import os
import sys
import asyncio
from pathlib import Path

# Add backend directory to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "backend"))

from backend.main import ocr_endpoint

async def test_ocr():
    test_pdf_path = root_dir / "scratch" / "test_single_page.pdf"
    print(f"Reading test PDF from: {test_pdf_path}")
    
    with open(test_pdf_path, "rb") as f:
        file_bytes = f.read()
        
    # Mock FastAPI UploadFile
    class MockFile:
        def __init__(self, filename, file_bytes):
            self.filename = filename
            import io
            self.file = io.BytesIO(file_bytes)
            
    mock_upload_file = MockFile("test_single_page.pdf", file_bytes)
    
    print("Calling ocr_endpoint...")
    # Since ocr_endpoint expects UploadFile, we pass mock_upload_file (duck typing works for .file, .filename)
    response = await ocr_endpoint(mock_upload_file)
    
    print("\nResponse:")
    import pprint
    pprint.pprint(response)
    
    assert "text" in response
    assert response["confidence"] == 1.0
    print("\nOCR Endpoint successfully verified!")

if __name__ == "__main__":
    asyncio.run(test_ocr())
