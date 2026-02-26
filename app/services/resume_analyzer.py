"""Resume analysis using LangChain with structured output (Pydantic)."""

from typing import Any

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.exceptions import BadRequestError
from app.core.logging import get_logger

log = get_logger(__name__)


class ResumeAnalysisSchema(BaseModel):
    """Structured output schema for resume analysis (LangChain)."""

    summary: str = Field(description="2-4 sentence professional summary of the candidate")
    skills: list[str] = Field(default_factory=list, description="Technical and soft skills, e.g. Python, Project Management")
    experience_years: float | None = Field(default=None, description="Total years of work experience if inferable, else null")
    education: list[str] = Field(default_factory=list, description="Degrees and certifications, e.g. B.Tech Computer Science - XYZ University")
    job_titles: list[str] = Field(default_factory=list, description="Roles held, e.g. Software Engineer, Intern")
    resume_score: int | None = Field(default=None, description="Overall resume strength 0-100 based on clarity, relevance, experience; null if not inferable")
    suggested_job_titles: list[str] = Field(default_factory=list, description="Job titles to apply for based on profile, e.g. Senior Software Engineer, Backend Developer")
    target_recruiter_roles: list[str] = Field(default_factory=list, description="Recruiter/HR roles to contact, e.g. HR Manager, Talent Acquisition, Recruiter")


RESUME_ANALYSIS_SYSTEM = """You are an expert resume analyst. Extract structured information from the resume text.
Fill every field based on the content. Use empty list or null only when the information is not present in the resume.
For resume_score give an integer 0-100 based on clarity, completeness, and relevance. For suggested_job_titles recommend 3-5 roles the candidate could apply for. For target_recruiter_roles list who they should contact (e.g. HR Manager, Recruiter, Talent Acquisition)."""

RESUME_ANALYSIS_USER_TEMPLATE = """Extract the following from this resume text:

{resume_text}"""


def analyze_resume_with_openai(raw_text: str) -> dict[str, Any]:
    """
    Use LangChain ChatOpenAI with structured output (Pydantic) to extract resume data.
    Returns dict with summary, skills, experience_years, education, job_titles.
    """
    settings = get_settings()
    if not settings.openai_api_key or not settings.openai_api_key.strip():
        log.warning("analyze_resume_with_openai_no_key")
        raise BadRequestError("OpenAI API key not configured; cannot analyze resume")
    raw_text = (raw_text or "").strip()[:12000]
    if not raw_text:
        return _empty_analysis()

    log.info("analyze_resume_with_openai_start", text_len=len(raw_text))
    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=settings.openai_api_key.strip(),
            temperature=0.2,
            max_tokens=1500,
        )
        structured_llm = llm.with_structured_output(ResumeAnalysisSchema)
        prompt = ChatPromptTemplate.from_messages([
            ("system", RESUME_ANALYSIS_SYSTEM),
            ("human", RESUME_ANALYSIS_USER_TEMPLATE),
        ])
        chain = prompt | structured_llm
        result: ResumeAnalysisSchema = chain.invoke({"resume_text": raw_text})

        out = {
            "summary": (result.summary or "").strip(),
            "skills": [s.strip() for s in (result.skills or []) if s and s.strip()],
            "experience_years": float(result.experience_years) if result.experience_years is not None else None,
            "education": [e.strip() for e in (result.education or []) if e and e.strip()],
            "job_titles": [j.strip() for j in (result.job_titles or []) if j and j.strip()],
            "resume_score": int(result.resume_score) if result.resume_score is not None else None,
            "suggested_job_titles": [j.strip() for j in (result.suggested_job_titles or []) if j and j.strip()],
            "target_recruiter_roles": [r.strip() for r in (result.target_recruiter_roles or []) if r and r.strip()],
        }
        log.info(
            "analyze_resume_with_openai_ok",
            skills_count=len(out["skills"]),
            education_count=len(out["education"]),
        )
        return out
    except Exception as e:
        log.exception("analyze_resume_with_openai_error", reason=str(e)[:200])
        raise BadRequestError(f"Resume analysis failed: {e}") from e


def _empty_analysis() -> dict[str, Any]:
    return {
        "summary": "",
        "skills": [],
        "experience_years": None,
        "education": [],
        "job_titles": [],
        "resume_score": None,
        "suggested_job_titles": [],
        "target_recruiter_roles": [],
    }
