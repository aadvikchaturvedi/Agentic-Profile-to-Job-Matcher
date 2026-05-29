# backend/app/api/routes.py
from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from pypdf import PdfReader
import io
from app.models import AgentResponse
from app.agents.orchestrator import MultiAgentOrchestrator

router = APIRouter()

@router.post("/match", response_model=AgentResponse)
async def match_resume_to_jd(
    raw_job_description: str = Form(...),
    resume_file: UploadFile = File(...)
):
    # 1. Enforce safety checks on file extensions early
    if not resume_file.filename or not resume_file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF resumes are supported.")
    
    try:
        file_bytes = await resume_file.read()
        
        pdf_stream = io.BytesIO(file_bytes)
        reader = PdfReader(pdf_stream)
        
        extracted_text = ""
        for page in reader.pages:
            extracted_text += page.extract_text() or ""
            
        if not extracted_text.strip():
            raise HTTPException(status_code=400, detail="The uploaded PDF file is empty or unreadable.")
            
        orchestrator = MultiAgentOrchestrator()
        final_agent_report = orchestrator.run(
            resume_text=extracted_text, 
            jd_text=raw_job_description
        )
        
        return final_agent_report
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Processing Error: {str(e)}")
    
