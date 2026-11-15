import * as pdfjs from './vendor/pdf.mjs';

pdfjs.GlobalWorkerOptions.workerSrc = new URL('./vendor/pdf.worker.mjs', import.meta.url).href;
const $ = id => document.getElementById(id);
const MAX_BYTES = 10 * 1024 * 1024;
const MAX_PAGES = 25;
let inputFile = null;
let result = null;
let generation = 0;
let worker = null;
let workerPromise = null;
let pdfTask = null;
let downloadURL = null;
let previewURLs = [];
let busy = false;

function status(message, state = 'idle', progress = null) {
  $('status-text').textContent = message;
  $('status').dataset.state = state;
  $('progress-track').hidden = progress === null;
  if (progress !== null) $('progress-bar').style.width = `${Math.min(100, Math.max(0, progress * 100))}%`;
}

function setBusy(value) {
  busy = value;
  $('parse').disabled = value || !inputFile;
  $('parse').firstChild.textContent = value ? 'Reading your document… ' : 'Parse document ';
  $('file-input').disabled = value;
  document.querySelectorAll('[data-example]').forEach(button => { button.disabled = value; });
}

function clearResults() {
  result = null;
  if (downloadURL) URL.revokeObjectURL(downloadURL);
  previewURLs.forEach(url => URL.revokeObjectURL(url));
  previewURLs = [];
  downloadURL = null;
  $('download').removeAttribute('href');
  $('download').setAttribute('aria-disabled', 'true');
  $('result-content').hidden = true;
  $('empty-state').hidden = false;
  ['canonical-text', 'quality-json', 'mapping-json', 'result-meta'].forEach(id => { $(id).textContent = ''; });
  $('page-select').replaceChildren();
  const canvas = $('source-preview');
  canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
}

async function cancel() {
  generation++;
  if (pdfTask) { try { await pdfTask.destroy(); } catch {} pdfTask = null; }
  if (worker) { try { await worker.terminate(); } catch {} worker = null; }
  workerPromise = null;
  setBusy(false);
}

async function chooseFile(file) {
  await cancel();
  clearResults();
  inputFile = file || null;
  $('file-card').hidden = !inputFile;
  if (inputFile) {
    $('file-name').textContent = inputFile.name;
    $('file-size').textContent = `${(inputFile.size / 1024).toLocaleString(undefined, { maximumFractionDigits: 1 })} KiB`;
    status('Document selected. Choose Parse document to inspect it.');
  } else {
    $('file-input').value = '';
    status('Ready when you are. Choose a document to begin.');
  }
  $('parse').disabled = !inputFile;
}

function checkGeneration(id) {
  if (id !== generation) throw new Error('CANCELLED');
}

function detectMime(bytes) {
  if (bytes.length >= 5 && String.fromCharCode(...bytes.slice(0, 5)) === '%PDF-') return 'application/pdf';
  if (bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255) return 'image/jpeg';
  if ([137, 80, 78, 71, 13, 10, 26, 10].every((value, i) => bytes[i] === value)) return 'image/png';
  throw new Error('Unsupported file content. Choose a PDF, JPEG or PNG; renaming a file does not convert it.');
}

async function sha256(bytes) {
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map(n => n.toString(16).padStart(2, '0')).join('');
}

function nativePage(items, number) {
  let text = '';
  let lastY = null;
  const mappings = [];
  for (const [index, item] of items.entries()) {
    if (!('str' in item) || !item.str) continue;
    const y = item.transform[5];
    const newLine = lastY !== null && Math.abs(y - lastY) > Math.max(2, item.height * 0.5);
    if (text && !text.endsWith('\n')) text += newLine ? '\n' : ' ';
    const start = text.length;
    text += item.str;
    mappings.push({ page: number, item: `pdf-text-${index}`, start, end: text.length, text: item.str,
      method: 'pdf-native-text-item', coordinates: { system: 'pdf-points', transform: item.transform, width: item.width, height: item.height } });
    if (item.hasEOL) text += '\n';
    lastY = y;
  }
  return { text, mappings };
}

async function ocrWorker(id, base, span) {
  if (worker) return worker;
  status('Loading the English OCR engine for this browser. Your document stays local.', 'working', base);
  if (!window.Tesseract) throw new Error('The OCR library did not load. Check your connection and reload the demo.');
  if (!workerPromise) {
    workerPromise = window.Tesseract.createWorker('eng', 1, {
      workerPath: new URL('./vendor/worker.min.js', import.meta.url).href,
      corePath: 'https://cdn.jsdelivr.net/npm/tesseract.js-core@7.0.0',
      langPath: 'https://tessdata.projectnaptha.com/4.0.0',
      workerBlobURL: false,
      logger: event => { if (id === generation) status(event.status === 'recognizing text' ? 'Recognizing page text in this browser…' : 'Preparing English OCR…', 'working', base + span * (event.progress || 0)); },
    });
  }
  const created = await workerPromise;
  if (id !== generation) { await created.terminate(); throw new Error('CANCELLED'); }
  worker = created;
  await worker.setParameters({ preserve_interword_spaces: '1' });
  return worker;
}

function ocrPage(data, number) {
  const lines = (data.blocks || []).flatMap(block => (block.paragraphs || []).flatMap(paragraph => paragraph.lines || []));
  let text = '';
  const mappings = [];
  for (const [index, line] of lines.entries()) {
    const value = (line.text || (line.words || []).map(word => word.text).join(' ')).trimEnd();
    if (!value) continue;
    if (text) text += '\n';
    const start = text.length;
    text += value;
    mappings.push({ page: number, item: `ocr-line-${index}`, start, end: text.length, text: value,
      method: 'tesseract-recognized-line', coordinates: line.bbox ? { system: 'rendered-image-pixels', box: line.bbox } : null });
  }
  if (!lines.length && data.text) {
    text = data.text;
    mappings.push({ page: number, item: 'ocr-page', start: 0, end: text.length, text, method: 'tesseract-recognized-page', coordinates: null });
  }
  return { text, mappings };
}

function isBlank(canvas) {
  const pixels = canvas.getContext('2d', { willReadFrequently: true }).getImageData(0, 0, canvas.width, canvas.height).data;
  let low = 255, high = 0;
  for (let i = 0; i < pixels.length; i += 4) {
    const gray = (pixels[i] + pixels[i + 1] + pixels[i + 2]) / 3;
    low = Math.min(low, gray); high = Math.max(high, gray);
    if (low < 245 || high - low > 3) return false;
  }
  return true;
}

async function inspectPage(canvas, native, raster, number, id, count) {
  const base = (number - 1) / count;
  checkGeneration(id);
  let parsed = native;
  let confidence = null;
  let method = 'native_pdf';
  const warnings = [];
  const nativeLetters = native.text.replace(/\s/g, '').length;
  if (raster || nativeLetters < 20) {
    method = 'english_ocr';
    if (isBlank(canvas)) parsed = { text: '', mappings: [] };
    else {
      const engine = await ocrWorker(id, base, 0.9 / count);
      const { data } = await engine.recognize(canvas, {}, { text: true, blocks: true });
      checkGeneration(id);
      confidence = data.confidence;
      parsed = ocrPage(data, number);
      if (confidence < 80) warnings.push('Low OCR confidence; compare all values with the original.');
    }
  }
  const state = parsed.text.trim() ? 'readable_text' : isBlank(canvas) ? 'blank' : 'unreadable';
  if (state === 'blank') warnings.push('Blank page: no readable content.');
  if (state === 'unreadable') warnings.push('No text was recovered from a nonblank page. Try a clearer source.');
  if (method === 'english_ocr') warnings.push('English OCR may misread layout, amounts, dates or other languages.');
  if (raster && nativeLetters >= 20) warnings.push('Raster content detected: full-page OCR used to avoid dropping a scanned body.');
  status(`Preparing source locations for page ${number} of ${count}…`, 'working', number / count * 0.95);
  const image = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
  checkGeneration(id);
  const preview = URL.createObjectURL(image);
  previewURLs.push(preview);
  return { page: number, text: parsed.text, mappings: parsed.mappings, method, ocr_confidence: confidence,
    state, needs_review: true, warnings, preview, width: canvas.width, height: canvas.height };
}

async function parsePDF(bytes, id) {
  pdfTask = pdfjs.getDocument({ data: bytes.slice(), isEvalSupported: false,
    cMapUrl: new URL('./vendor/cmaps/', import.meta.url).href, cMapPacked: true,
    standardFontDataUrl: 'https://cdn.jsdelivr.net/npm/pdfjs-dist@6.5.438/standard_fonts/' });
  let passwordReject;
  const passwordFailure = new Promise((_, reject) => { passwordReject = reject; });
  pdfTask.onPassword = () => { passwordReject(new Error('Password-protected PDFs are not supported. Provide an unlocked original.')); };
  let pdf;
  try { pdf = await Promise.race([pdfTask.promise, passwordFailure]); }
  catch (error) { await pdfTask.destroy(); pdfTask = null; throw error; }
  try {
    if (pdf.numPages > MAX_PAGES || pdf.numPages < 1) throw new Error('PDFs must contain 1–25 pages. No pages were parsed or silently truncated.');
    const pages = [];
    for (let number = 1; number <= pdf.numPages; number++) {
      checkGeneration(id);
      status(`Reading page ${number} of ${pdf.numPages}…`, 'working', (number - 1) / pdf.numPages);
      const page = await pdf.getPage(number);
      const original = page.getViewport({ scale: 1 });
      const scale = Math.min(2, 1800 / Math.max(original.width, original.height));
      const viewport = page.getViewport({ scale });
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.ceil(viewport.width)); canvas.height = Math.max(1, Math.ceil(viewport.height));
      // A static preview should also render when its tab/frame is offscreen.
      status(`Rendering the original · page ${number} of ${pdf.numPages}…`, 'working', (number - 1) / pdf.numPages);
      await page.render({ canvasContext: canvas.getContext('2d'), viewport, background: '#ffffff', intent: 'print' }).promise;
      status(`Extracting native text · page ${number} of ${pdf.numPages}…`, 'working', (number - 1) / pdf.numPages);
      const content = await page.getTextContent();
      status(`Checking page layout · page ${number} of ${pdf.numPages}…`, 'working', (number - 1) / pdf.numPages);
      const operators = await page.getOperatorList();
      const imageOps = new Set(['paintImageXObject', 'paintInlineImageXObject', 'paintImageMaskXObject', 'paintImageXObjectRepeat', 'paintImageMaskXObjectRepeat'].map(key => pdfjs.OPS[key]).filter(value => value !== undefined));
      const raster = operators.fnArray.some(op => imageOps.has(op));
      pages.push(await inspectPage(canvas, nativePage(content.items, number), raster, number, id, pdf.numPages));
      canvas.width = 0; canvas.height = 0;
      page.cleanup();
    }
    return pages;
  } finally { status('Finishing PDF inspection…', 'working', .98); if (pdfTask) await pdfTask.destroy(); pdfTask = null; }
}

async function parseImage(bytes, mime, id) {
  const bitmap = await createImageBitmap(new Blob([bytes], { type: mime }), { imageOrientation: 'from-image' });
  try {
    if (bitmap.width * bitmap.height > 80000000) throw new Error('This image is too large to decode safely in the demo. Export a smaller image.');
    const scale = Math.min(1, 2200 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.ceil(bitmap.width * scale); canvas.height = Math.ceil(bitmap.height * scale);
    const context = canvas.getContext('2d');
    context.fillStyle = '#ffffff'; context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return [await inspectPage(canvas, { text: '', mappings: [] }, true, 1, id, 1)];
  } finally { bitmap.close(); }
}

async function showPage() {
  if (!result) return;
  const page = result.pages[Number($('page-select').value) || 0];
  $('canonical-text').textContent = page.text || `[${page.state === 'blank' ? 'Blank page' : 'No readable text recovered'}]`;
  $('mapping-json').textContent = JSON.stringify(page.mappings, null, 2);
  $('page-method').textContent = page.method === 'native_pdf' ? 'Native PDF text' : `English OCR${page.ocr_confidence === null ? '' : ` · ${Math.round(page.ocr_confidence)}% confidence`}`;
  const image = new Image();
  image.src = page.preview;
  await image.decode();
  if (!result || !previewURLs.includes(page.preview)) return;
  const canvas = $('source-preview');
  canvas.width = image.width; canvas.height = image.height;
  canvas.getContext('2d').drawImage(image, 0, 0);
}

async function runParsing() {
  if (!inputFile || busy) return;
  clearResults(); setBusy(true);
  const id = ++generation;
  const started = performance.now();
  try {
    if (inputFile.size === 0) throw new Error('This file is empty. Choose a readable document.');
    if (inputFile.size > MAX_BYTES) throw new Error('This file exceeds 10 MiB. Choose a smaller document; it was not parsed.');
    status('Checking document bytes…', 'working', 0);
    const bytes = new Uint8Array(await inputFile.arrayBuffer());
    checkGeneration(id);
    const mime = detectMime(bytes);
    const digest = await sha256(bytes);
    const pages = mime === 'application/pdf' ? await parsePDF(bytes, id) : await parseImage(bytes, mime, id);
    checkGeneration(id);
    if (!pages.length) throw new Error('No pages could be read.');
    for (const page of pages) for (const span of page.mappings) {
      if (page.text.slice(span.start, span.end) !== span.text) throw new Error('Source mapping validation failed. No result was exported.');
    }
    const seconds = (performance.now() - started) / 1000;
    const problematic = pages.filter(page => page.state !== 'readable_text');
    const report = { format: 'claimly-browser-parsing-v1', serializer: 'claimly-browser-page-spans-v1',
      engines: { pdfjs: '6.5.438', tesseract: '7.0.0', ocr_language: 'eng', docling: false },
      source: { filename: inputFile.name, mime_type: mime, bytes: bytes.length, sha256: digest },
      page_count: pages.length, processed_page_count: pages.length,
      elapsed_seconds: Math.round(seconds * 1000) / 1000, source_review: 'required',
      relevance: 'not_evaluated', admission: 'not_performed', document_uploads: 0, hosted_model_calls: 0,
      quality: { complete_page_coverage: true, readable_pages: pages.length - problematic.length,
        blank_pages: pages.filter(page => page.state === 'blank').length,
        unreadable_pages: pages.filter(page => page.state === 'unreadable').length,
        note: 'Conversion checks are not proof of OCR correctness or Claimly relevance. Source review remains required.' },
      pages: pages.map(({ preview, ...page }) => page) };
    result = { pages, report };
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    downloadURL = URL.createObjectURL(blob);
    $('download').href = downloadURL; $('download').setAttribute('aria-disabled', 'false');
    $('page-select').replaceChildren(...pages.map((page, index) => {
      const option = document.createElement('option'); option.value = index; option.textContent = `${page.page} of ${pages.length}`; return option;
    }));
    $('quality-json').textContent = JSON.stringify({ ...report, pages: pages.map(page => ({ page: page.page, method: page.method, state: page.state, warnings: page.warnings, ocr_confidence: page.ocr_confidence })) }, null, 2);
    $('coverage-value').textContent = `${pages.length} / ${pages.length} pages`;
    $('result-meta').textContent = `${pages.length} ${pages.length === 1 ? 'page' : 'pages'} · ${seconds.toFixed(1)}s · source review required`;
    $('result-content').hidden = false; $('empty-state').hidden = true;
    await showPage();
    status(problematic.length ? 'Review required. One or more pages are blank or unreadable.' : 'Parsing complete. Compare the text with the original before relying on it.', problematic.length ? 'review' : 'complete');
  } catch (error) {
    if (id !== generation) return;
    clearResults();
    const message = error?.name === 'InvalidPDFException' ? 'This PDF is damaged or unsupported. Provide a valid original.'
      : error?.message?.includes('Password') ? 'Password-protected PDFs are not supported. Provide an unlocked original.'
        : error?.message || 'Parsing could not finish. Try a clearer or smaller document.';
    status(message === 'CANCELLED' ? 'Parsing cancelled.' : message, 'error');
  } finally {
    if (id === generation) {
      if (worker) { try { await worker.terminate(); } catch {} worker = null; }
      workerPromise = null;
      setBusy(false);
    }
  }
}

$('file-input').addEventListener('change', event => chooseFile(event.target.files[0]));
$('parse').addEventListener('click', runParsing);
$('clear').addEventListener('click', () => chooseFile(null));
$('remove-file').addEventListener('click', () => chooseFile(null));
$('page-select').addEventListener('change', showPage);
$('copy').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText($('canonical-text').textContent); $('copy').textContent = 'Copied'; setTimeout(() => { $('copy').textContent = 'Copy'; }, 1800); }
  catch { status('Copy is unavailable in this browser. Select the text, or download the JSON report.', 'review'); }
});
document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('[data-tab]').forEach(tab => tab.setAttribute('aria-selected', String(tab === button)));
  ['text', 'quality', 'mapping'].forEach(name => { $(`view-${name}`).hidden = name !== button.dataset.tab; });
}));
document.querySelectorAll('[data-example]').forEach(button => button.addEventListener('click', async () => {
  try {
    const response = await fetch(`examples/${button.dataset.example}`);
    if (!response.ok) throw new Error('The example could not be loaded. Please try uploading a file.');
    const blob = await response.blob();
    await chooseFile(new File([blob], button.dataset.example, { type: blob.type }));
    await runParsing();
  } catch (error) { status(error.message, 'error'); }
}));
$('dropzone').addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); if (!busy) $('file-input').click(); } });
$('dropzone').addEventListener('dragover', event => { event.preventDefault(); if (!busy) $('dropzone').classList.add('dragover'); });
$('dropzone').addEventListener('dragleave', () => $('dropzone').classList.remove('dragover'));
$('dropzone').addEventListener('drop', event => {
  event.preventDefault(); $('dropzone').classList.remove('dragover');
  if (!busy) chooseFile(event.dataTransfer.files[0]);
});
window.addEventListener('beforeunload', () => { previewURLs.forEach(url => URL.revokeObjectURL(url)); if (downloadURL) URL.revokeObjectURL(downloadURL); worker?.terminate(); });
document.documentElement.dataset.parserReady = 'true';
status('Ready when you are. Choose a document to begin.');
if ($('file-input').files.length) chooseFile($('file-input').files[0]);
