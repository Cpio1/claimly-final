"""Claimly document parsing demo. Run from the generated Space release bundle."""
import spaces  # Must precede Docling/torch imports, even for CPU-only parsing.
import logging
import os
import threading
from pathlib import Path

os.environ.setdefault('OMP_NUM_THREADS', '2')
os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
os.environ['GRADIO_ANALYTICS_ENABLED'] = 'False'
os.environ.setdefault('GRADIO_TEMP_DIR', '/tmp/gradio')

import gradio as gr
from assets import ROOT, ASSET_ROOT, prepare_assets

logging.basicConfig(level=logging.WARNING)
logging.getLogger('claimly_parser').setLevel(logging.ERROR)
prepare_assets()
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

from demo_engine import clean_expired, parse_source
from claimly_parser import InvalidSource

threading.Thread(target=clean_expired, daemon=True).start()
print('Claimly parser ready: pinned assets verified; CPU parsing; no hosted inference.', flush=True)


@spaces.GPU(duration=1)
def runtime_marker() -> str:
    """Private, unused marker required by free CPU-only ZeroGPU Spaces."""
    return 'CPU parser does not call this function.'


def parse_document(file_path: str) -> tuple:
    """Inspect PDF/JPEG/PNG text and provenance, without approving or indexing it.

    Args:
        file_path: Uploaded document, up to 10 MiB and 25 PDF pages.
    Returns:
        Status, original-page previews, canonical text, quality report, exact item
        mappings and a ZIP containing Docling/canonical JSON and source identity.
    """
    try:
        return parse_source(file_path)
    except InvalidSource as exc:
        return 'Document could not be parsed.', [], '', {'status': 'invalid_file', 'reason': str(exc)}, [], None
    except Exception as exc:
        logging.getLogger(__name__).error('parse_failed exception_type=%s', type(exc).__name__)
        return ('Parsing could not finish. Try a clearer or smaller document.', [], '',
                {'status': 'conversion_error', 'reason': 'Conversion failed; no source was admitted.'}, [], None)


CSS = """
.gradio-container { max-width: 1320px !important; margin: auto !important; }
.dark .gradio-container { color: var(--body-text-color); }
#intro { padding: 18px 0 10px; }
#status { border-left: 3px solid #2563eb; padding-left: 14px; }
"""

with gr.Blocks(title='Claimly · Document parser', delete_cache=(300, 3600)) as demo:
    gr.Markdown('# Claimly · Document parser\nRead the document. Check the source.', elem_id='intro')
    gr.Markdown('Turn a PDF or image into page text, tables and traceable source locations. Start with a fictional example or upload a redacted document.')
    with gr.Row():
        with gr.Column(scale=1, min_width=280):
            upload = gr.File(label='Your document', file_types=['.pdf', '.jpg', '.jpeg', '.png'], type='filepath')
            gr.Markdown('**PDF · JPEG · PNG** &nbsp; Up to 10 MiB · 25 pages')
            run = gr.Button('Parse document', variant='primary')
            clear = gr.ClearButton(value='Clear document')
            gr.Examples(
                examples=[[str(ROOT / 'examples' / name)] for name in ['warranty.pdf', 'scan_pdf.pdf', 'table_bill.pdf', 'multipage_contract.pdf', 'png_scan.png']],
                example_labels=['Warranty · text PDF', 'Warranty · scanned PDF', 'Bill · table', 'Contract · two pages', 'Warranty · PNG scan'],
                inputs=[upload], label='Try a fictional example', cache_examples=False,
            )
            gr.Markdown('### Before you upload\nFiles are processed on this Space and cached temporarily, with cleanup after one hour. Use fictional or redacted documents. Nothing is added to your Vault.')
        with gr.Column(scale=3, min_width=320):
            status = gr.Markdown('**Ready when you are.** Choose a document, then select Parse document.', elem_id='status')
            with gr.Tab('Source & text'):
                with gr.Row():
                    gallery = gr.Gallery(label='Original pages', columns=1, height=600, object_fit='contain', show_download_button=False)
                    text = gr.Textbox(label='Canonical page text', lines=26, max_lines=40, interactive=False, show_copy_button=True)
            with gr.Tab('Quality checks'):
                gr.Markdown('These checks assess conversion and page coverage. They do not establish relevance or prove that OCR values are correct.')
                report = gr.JSON(label='Conversion report')
            with gr.Tab('Source locations'):
                gr.Markdown('Character offsets refer to the canonical page text. They are not PDF byte offsets. Each record resolves to a Docling item and page.')
                mappings = gr.JSON(label='Exact item-to-page mappings')
            download = gr.File(label='Download inspection bundle · JSON ZIP', interactive=False)
            gr.Markdown('**Source review is still required.** Parsing does not classify relevance, approve a source, infer benefits or answer legal questions.')
    outputs = [status, gallery, text, report, mappings, download]
    run.click(parse_document, inputs=[upload], outputs=outputs, api_name='parse_document', concurrency_limit=1, concurrency_id='parser')
    clear.add([upload, gallery, text, report, mappings, download])
    clear.click(fn=lambda: 'Ready when you are. Choose a document, then select Parse document.', outputs=[status], api_name=False, queue=False)
    marker = gr.Button(visible=False)
    marker.click(runtime_marker, inputs=[], outputs=[], api_name=False)
    gr.Markdown('Built with Docling + RapidOCR · CPU processing · No hosted-model calls')

demo.queue(max_size=8, default_concurrency_limit=1)

if __name__ == '__main__':
    demo.launch(theme=gr.themes.Soft(), css=CSS, mcp_server=True,
                max_file_size='10mb', blocked_paths=[str(ASSET_ROOT), str(ROOT / 'ocr_assets')],
                show_error=False)
