import re

import fitz

from chain_eye.domain.extraction import DocumentBlock,DocumentPage,DocumentPages,DocumentWord,ExtractionError

NUMBER=re.compile(r'-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?')

class PyMuPDFParser:
    def parse(self,source_id,content):
        try:
            with fitz.open(stream=content,filetype='pdf') as document:
                if document.needs_pass or document.is_encrypted:raise ExtractionError('encrypted PDF')
                pages=[]
                for index,page in enumerate(document):
                    text=page.get_text('text',sort=True)
                    words=tuple(DocumentWord(text=value[4],bbox=tuple(float(v) for v in value[:4])) for value in page.get_text('words',sort=True))
                    blocks=tuple(DocumentBlock(text=value[4].strip(),bbox=tuple(float(v) for v in value[:4])) for value in page.get_text('blocks',sort=True) if value[4].strip())
                    tables=tuple(line.strip() for line in text.splitlines() if len(NUMBER.findall(line))>=2)
                    warnings=() if text.strip() else ('page_has_no_text_layer',)
                    pages.append(DocumentPage(page_no=index+1,text=text,words=words,blocks=blocks,table_candidates=tables,parse_warnings=warnings))
        except ExtractionError:raise
        except Exception as exc:raise ExtractionError('PDF text parsing failed') from exc
        return DocumentPages(source_id=source_id,page_count=len(pages),pages=tuple(pages))
