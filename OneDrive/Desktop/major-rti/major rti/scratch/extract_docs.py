"""Script to extract text from .doc and .pdf reference documents"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 1) Extract sample-rti-response.doc via win32com
print("Extracting sample-rti-response.doc...")
try:
    import win32com.client
    import os
    word = win32com.client.Dispatch('Word.Application')
    word.Visible = False
    doc_path = os.path.abspath(r'sample-rti-response.doc')
    doc = word.Documents.Open(doc_path)
    text = doc.Content.Text
    doc.Close(False)
    word.Quit()
    with open(r'scratch/sample_response2.txt', 'w', encoding='utf-8') as f:
        f.write(text)
    print(f'Done - extracted {len(text)} chars via win32com')
except Exception as e:
    print(f'win32com failed: {e}')
    print('Trying binary extraction...')
    with open(r'sample-rti-response.doc', 'rb') as f:
        data = f.read()
    # Extract text from compound doc binary
    import struct
    text_chunks = []
    i = 0
    while i < len(data) - 1:
        # Look for Unicode text (UTF-16LE)
        char = data[i:i+2]
        try:
            c = char.decode('utf-16-le')
            if c.isprintable() or c in '\n\r\t':
                text_chunks.append(c)
            else:
                if len(text_chunks) > 0 and text_chunks[-1] != '\n':
                    text_chunks.append('\n')
        except:
            if len(text_chunks) > 0 and text_chunks[-1] != '\n':
                text_chunks.append('\n')
        i += 2
    raw = ''.join(text_chunks)
    # Keep lines with meaningful content
    lines = [l.strip() for l in raw.split('\n') if len(l.strip()) > 3]
    result = '\n'.join(lines)
    with open(r'scratch/sample_response2.txt', 'w', encoding='utf-8') as f:
        f.write(result)
    print(f'Done - extracted {len(lines)} lines via binary parse')

# 2) Read first 50 pages of RTI rulebook
print("\nReading RTI rulebook key pages...")
import PyPDF2
with open(r'rti-rule-book.pdf', 'rb') as f:
    reader = PyPDF2.PdfReader(f)
    print(f'Total pages: {len(reader.pages)}')
    with open(r'scratch/rti_rulebook_key.txt', 'w', encoding='utf-8') as out:
        for i in range(min(60, len(reader.pages))):
            text = reader.pages[i].extract_text()
            if text and len(text.strip()) > 20:
                out.write(f'\n=== PAGE {i+1} ===\n')
                out.write(text)
    print('Done - rti_rulebook_key.txt created')
