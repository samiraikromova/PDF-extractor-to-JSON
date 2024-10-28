import json
import logging
import re
from pathlib import Path
from typing import Dict, Any, Tuple
import pymupdf as fitz

logging.basicConfig(level=logging.INFO)

PDF_PATH = "Руководство_Бухгалтерия_для_Узбекистана_ред_3_0.pdf"


class PDFProcessor:

    def __init__(self, pdf_path: str, start_page: int = 13):
        self.pdf_path = pdf_path
        self.start_page = start_page
        self.structure = self._extract_structure()
        self.text = ''
        self.current_dir = Path(__file__).resolve().parent

    @staticmethod
    def _prepare_regex(title: str) -> str:
        return re.escape(title).replace('\\ ', '\\s*')

    def _set_section_text(self, prev_level: dict, section_text: str):
        length = len(section_text.strip())

        # Set the text for the respective level (chapter, section, or subsection)
        if prev_level['level'] == 'subsection':
            chapter = prev_level['chapter']
            section = prev_level['section']
            subsection = prev_level['subsection']
            self.structure[chapter]['sections'][section]['subsections'][subsection]['text'] = section_text
        elif prev_level['level'] == 'section':
            chapter = prev_level['chapter']
            section = prev_level['section']
            self.structure[chapter]['sections'][section]['text'] = section_text
        elif prev_level['level'] == 'chapter':
            chapter = prev_level['chapter']
            self.structure[chapter]['text'] = section_text

    def _extract_text(self):
        text_list = []
        with fitz.open(self.pdf_path) as doc:
            for page_num in range(self.start_page - 1, len(doc)):
                page = doc.load_page(page_num)
                page_text = page.get_text("text")
                if page_text:
                    text_list.append(page_text)
        self.text = '\n'.join(text_list)
        logging.info("Text extraction complete.")

    def _match_structure(self):
        prev_match_end = 0
        prev_level = {'level': 'start'}

        for chapter_num, chapter_dict in self.structure.items():
            # Regex for chapter
            chapter_title_regex = self._prepare_regex(chapter_dict.get('title', ''))
            chapter_regex = rf"(?i)Глава\s*{chapter_num}\s*{chapter_title_regex}"
            match = re.search(chapter_regex, self.text)
            if match:
                chapter_start = match.start()
                chapter_end = match.end()
                section_text = self.text[prev_match_end:chapter_start]
                if section_text.strip():
                    self._set_section_text(prev_level, section_text)
                prev_match_end = chapter_end
                prev_level = {'level': 'chapter', 'chapter': chapter_num}
            else:
                logging.warning(f"No match found for chapter: {chapter_num}")
                continue

            sections = chapter_dict.get('sections', {})
            for section_num, section_dict in sections.items():
                # Regex for section
                section_title_regex = self._prepare_regex(section_dict.get('title', ''))
                section_regex = rf"(?i)^{section_num}\s*{section_title_regex}"
                match = re.search(section_regex, self.text)
                if match:
                    section_start = match.start()
                    section_end = match.end()
                    section_text = self.text[prev_match_end:section_start]
                    if section_text.strip():
                        self._set_section_text(prev_level, section_text)
                    prev_match_end = section_end
                    prev_level = {
                        'level': 'section',
                        'chapter': chapter_num,
                        'section': section_num
                    }
                else:
                    logging.warning(f"No match found for section: {section_num}")
                    continue

                subsections = section_dict.get('subsections', {})
                for subsection_num, subsection_dict in subsections.items():
                    # Regex for subsection
                    subsection_title_regex = self._prepare_regex(subsection_dict.get('title', ''))
                    subsection_regex = rf"(?i)^{subsection_num}\s*{subsection_title_regex}"
                    match = re.search(subsection_regex, self.text)
                    if match:
                        subsection_start = match.start()
                        subsection_end = match.end()
                        subsection_text = self.text[prev_match_end:subsection_start]
                        if subsection_text.strip():
                            self._set_section_text(prev_level, subsection_text)
                        prev_match_end = subsection_end
                        prev_level = {
                            'level': 'subsection',
                            'chapter': chapter_num,
                            'section': section_num,
                            'subsection': subsection_num
                        }
                    else:
                        logging.warning(f"No match found for subsection: {subsection_num}")
                        continue

        # Process the last section
        if prev_match_end < len(self.text):
            section_text = self.text[prev_match_end:]
            self._set_section_text(prev_level, section_text)

        logging.info("Structure matching complete.")

    def _extract_structure(self) -> Dict[str, Any]:
        doc = fitz.open(self.pdf_path)
        toc = doc.get_toc()  # Get the table of contents

        structure = {}
        current_chapter = None
        current_section = None

        for level, title, page in toc:
            chapter_num, chapter_title = self._parse_chapter(title) if level == 1 else ("", "")
            section_num, section_title = self._parse_section(title) if level in [2, 3] and current_chapter else ("", "")

            if chapter_num:
                current_chapter = chapter_num
                structure[current_chapter] = {"title": chapter_title, "sections": {}}
                if not chapter_title:
                    next_item = toc[toc.index([level, title, page]) + 1] if toc.index(
                        [level, title, page]) + 1 < len(toc) else None
                    structure[current_chapter]["title"] = self._clean_text(next_item[1]) if next_item else ""

            elif section_num:
                if self._is_section(section_num):
                    current_section = section_num
                    if current_chapter not in structure:
                        structure[current_chapter] = {"title": "", "sections": {}}
                    structure[current_chapter]["sections"][current_section] = {"title": section_title,
                                                                               "subsections": {}}

                elif self._is_subsection(section_num):
                    if current_section and current_chapter in structure:
                        # Ensure current_section exists in the structure before accessing
                        if current_section not in structure[current_chapter]["sections"]:
                            structure[current_chapter]["sections"][current_section] = {"title": "", "subsections": {}}
                        structure[current_chapter]["sections"][current_section]["subsections"][section_num] = {
                            "title": section_title
                        }

        return structure

    def process_book(self) -> dict:
        self._extract_text()
        self._match_structure()
        return self.structure

    @staticmethod
    def _clean_text(text: str) -> str:
        """Cleans the text by removing extra whitespace."""
        if text is None:
            return ""
        cleaned_text = text.strip()  # Adjust cleaning logic as needed
        return cleaned_text

    def _parse_chapter(self, title: str) -> Tuple[str, str]:
        match = re.match(r'(Глава\s*)?(\d+)\.?\s*(.*)', title, re.IGNORECASE)
        if match:
            return match.group(2), self._clean_text(match.group(3))
        return "", self._clean_text(title)

    def _parse_section(self, title: str) -> Tuple[str, str]:
        match = re.match(r'^(\d+(\.\d+)?)(?:\.\s*)?(.*)', title)
        if match:
            return match.group(1), self._clean_text(match.group(3))
        return "", self._clean_text(title)

    @staticmethod
    def _is_section(section: str) -> bool:
        return bool(re.match(r'^\d+$', section))

    @staticmethod
    def _is_subsection(subsection: str) -> bool:
        return bool(re.match(r'^\d+\.\d+$', subsection))


def save_json(data: Dict[str, Any], output_path: str) -> None:
    with open(output_path, 'w', encoding='utf-8') as json_file:
        json.dump(data, json_file, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    processor = PDFProcessor(PDF_PATH)
    processor.process_book()  # Process the entire book
    output_json_path = Path(processor.current_dir) / "output_structure.json"
    save_json(processor.structure, str(output_json_path))  # Save the extracted structure as a JSON file
    logging.info("Structure saved successfully to output_structure.json.")
