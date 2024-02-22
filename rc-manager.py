#!/usr/bin/env python3
import os
import stat
import sys
import re
from typing import List
from argparse import ArgumentParser
from argparse import RawTextHelpFormatter
import textwrap


class ParserError(Exception):
    pass


class SectionNotFound(ParserError):
    pass


class SectionEndlessFound(ParserError):
    pass


class SectionEmptyFound(ParserError):
    pass


class SectionPatterns:
    def __init__(self):
        self.begin_prefix = None
        self.begin_suffix = None
        self.end_prefix = None
        self.end_suffix = None

        self.compiled_regex_generic_begin = None
        self.compiled_regex_generic_end = None

        # We define defaults here. Will be used in default values when
        # initializing ArgumentParser
        self.set_patterns('### [BEGIN ',
                          ']\n',
                          '### [END ',
                          ']\n')

    def set_patterns(self,
                     begin_prefix: str,
                     begin_suffix: str,
                     end_prefix: str,
                     end_suffix: str) -> None:
        self.begin_prefix = begin_prefix
        self.begin_suffix = begin_suffix
        self.end_prefix = end_prefix
        self.end_suffix = end_suffix

        escaped_begin_prefix = re.escape(begin_prefix)
        escaped_begin_suffix = re.escape(begin_suffix)
        escaped_end_prefix = re.escape(end_prefix)
        escaped_end_suffix = re.escape(end_suffix)

        self.compiled_regex_generic_begin = re.compile(
            f'{escaped_begin_prefix}.+{escaped_begin_suffix}'
        )
        self.compiled_regex_generic_end = re.compile(
            f'{escaped_end_prefix}.+{escaped_end_suffix}'
        )


def test_file_integrity(lines: List[str], sp: SectionPatterns) -> bool:
    sections_found = []
    sections_without_opening = []
    nested_session = None
    section = None
    section_line = None
    nested_section_line = None
    for i, line in enumerate(lines, start=1):
        if sp.compiled_regex_generic_begin.match(line) and not section:
            section = line[len(sp.begin_prefix):-len(sp.begin_suffix)]
            section_line = i
            continue
        if sp.compiled_regex_generic_begin.match(line) and section:
            nested_session = line[len(sp.begin_prefix):-len(sp.begin_suffix)]
            nested_section_line = i
            break
        if section and line == f'{sp.end_prefix}{section}{sp.end_suffix}':
            sections_found.append(section)
            section = None
            continue
        if not section and sp.compiled_regex_generic_end.match(line):
            sections_without_opening.append(line[:-1])

    if nested_session:
        print(f"Nested section '{nested_session}' (line {nested_section_line}) "
              f"inside section '{section}' (line {section_line}).", file=sys.stderr)
        print('Nested sections are not supported. Please fix them.', file=sys.stderr)
        print('Aborting', file=sys.stderr)
        exit(1)

    if section:
        print(f"Could not find end of section '{section}' (line {section_line}).", file=sys.stderr)
        return False

    if not sections_found:
        print('No sections found. Please double check prefix and suffix.', file=sys.stderr)
        return False

    print('Sections found:', file=sys.stderr)
    for section in sections_found:
        print(f'{section}')

    if sections_without_opening:
        print('', file=sys.stderr)
        print('Sections without opening:', file=sys.stderr)
        for section in sections_without_opening:
            print(f'{section}')
        return False
    return True


def get_section_content(section: str, lines: List[str], sp: SectionPatterns) -> List[str]:
    section_content = []
    cur_line = -1
    for line in lines:
        cur_line += 1
        if line == f'{sp.begin_prefix}{section}{sp.begin_suffix}':
            section_content.append(line)
            break
    else:
        raise SectionNotFound(f'{section}')

    cur_line += 1
    for line in lines[cur_line:]:
        section_content.append(line)
        if line == f'{sp.end_prefix}{section}{sp.end_suffix}':
            break
    else:
        raise SectionEndlessFound(f'{section}')

    if len(list(filter(lambda s: s.strip(), section_content))) == 2:
        raise SectionEmptyFound(f'{section}')

    return section_content


def main():
    sp = SectionPatterns()
    default_section_sep_in_cmd_line = ' '
    parser = ArgumentParser(prog='manage-configuration-files',
                            formatter_class=RawTextHelpFormatter,
                            description=textwrap.dedent('''\
Script to manage sections in configuration files like bashrc, bash_aliases,
vimrc...


        !!! WARNING !!!
DO NOT redirect the output of this program to its input.
You will lost the input file is you do so.

'''),
                            epilog='The output of this script will be in order as provided in options')
    parser.add_argument('-i', '--input-file',
                        dest='input_filename',
                        required=True,
                        help='File input content will be read from',
                        metavar='FILENAME')
    parser.add_argument('-t', '--test',
                        dest='test_file_integrity',
                        action='store_true',
                        help='Test against file integrity.\n'
                             '--sections and --section_separator_in_command_line\noptions will be ignored',
                        default=None,
                        required=False)
    parser.add_argument('-s', '--sections',
                        dest='sections',
                        help='Sections to look for. This is required only\nif -t, --test is not provided.',
                        required=False)
    parser.add_argument('--section_separator_in_command_line',
                        dest='section_separator_in_command_line',
                        help='Section separator when using weird names for sections.\n'
                             f"Defaults to '{default_section_sep_in_cmd_line}'.",
                        default=default_section_sep_in_cmd_line,
                        required=False)
    parser.add_argument('--section_begin_prefix',
                        dest='section_begin_prefix',
                        help=f"Defaults to '{sp.begin_prefix}'.",
                        default=sp.begin_prefix,
                        required=False)
    parser.add_argument('--section_begin_suffix',
                        dest='section_begin_suffix',
                        help=f"Defaults to '{sp.begin_suffix[:-1]}'.\n"
                             f"After this suffix, next char must be '\\n' in line.",
                        default=sp.begin_suffix,
                        required=False)
    parser.add_argument('--section_end_prefix',
                        dest='section_end_prefix',
                        help=f"Defaults to '{sp.end_prefix}'\n."
                             f"After this suffix, next char must be '\\n' in line.",
                        default=sp.end_prefix,
                        required=False)
    parser.add_argument('--section_end_suffix',
                        dest='section_end_suffix',
                        help=f"Defaults to '{sp.end_suffix[:-1]}'\n."
                             f"After this suffix, next char must be '\\n' in line.",
                        default=sp.end_suffix,
                        required=False)

    args = parser.parse_args()
    input_filename = args.input_filename

    sp.set_patterns(args.section_begin_prefix,
                    args.section_begin_suffix,
                    args.section_end_prefix,
                    args.section_end_suffix)

    try:
        with open(input_filename, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Could not read from file '{input_filename}': {e.__class__.__name__}.", file=sys.stderr)
        exit(1)

    if args.test_file_integrity:
        exit(0 if test_file_integrity(lines, sp) else 1)

    sections = args.sections.split(args.section_separator_in_command_line)

    if len(sections) == 0:
        print('No section selected. Please provide at least one section.', file=sys.stderr)
        exit(1)

    file_content_as_list = []
    current_line = 0
    for i, section in enumerate(sections):
        # At the end of this loop, we will append a \n so sections will not be
        # immediately followed one by another. The last one, at the end of the file
        # is going to be removed once the loop ends.
        # The following -i means how many \n we have already manually inserted.
        current_line += len(file_content_as_list) - i
        try:
            section_content = get_section_content(section, lines, sp)
        except SectionNotFound as e:
            print(f"Section not found '{e}'", file=sys.stderr)
            exit(1)
        except SectionEndlessFound as e:
            print(f"Could not find end of section '{e}'", file=sys.stderr)
            exit(1)
        except SectionEmptyFound as e:
            print(f"Section is empty '{e}'", file=sys.stderr)
            exit(1)

        file_content_as_list.extend(section_content)
        file_content_as_list.append('\n')

    file_content_as_list.pop()  # Last \n in not necessary.
    file_content = ''.join(file_content_as_list)

    with open('/dev/stdout', 'w') as f:
        f.write(file_content)


if __name__ == '__main__':
    main()
    exit(0)
