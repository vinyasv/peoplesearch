from typing import Literal

from pydantic import BaseModel, Field


class Criterion(BaseModel):
    id: str = Field(description="Short snake_case identifier, e.g. 'profession' or 'threejs_experience'.")
    label: str = Field(
        description="Short table column header, 1-3 words, e.g. 'Profession', 'Based in NYC', 'three.js', "
        "'4+ years', '1k+ stars'. The full condition goes in `requirement`."
    )
    requirement: str = Field(
        description="The precise, checkable condition, e.g. 'Currently works as a software engineer'."
    )
    kind: Literal["hard", "soft"] = Field(
        description="hard = the user explicitly required it; soft = a preference or nice-to-have."
    )
    research_hints: str = Field(
        description="Where and how a researcher should look to confirm or deny this criterion."
    )
    public_record: bool = Field(
        default=False,
        description="True if meeting this criterion would normally leave a findable public record (talks, "
        "papers, funding rounds, acquisitions, open-source repos and stars, patents, awards), so a thorough "
        "search that finds nothing means it is not met. False for facts that may be private or simply "
        "unpublished (exact skills, tenure details, internal roles).",
    )


class SearchPlan(BaseModel):
    criteria: list[Criterion]
    exa_queries: list[str] = Field(
        description="2-4 natural-language queries for Exa's people search, each phrased as a "
        "description of the profile being looked for."
    )


class Candidate(BaseModel):
    id: str
    name: str
    profile_url: str
    linkedin_url: str | None = None
    headline: str | None = None
    location: str | None = None
    work_history: list[dict] = []
    profile_text: str = ""
    matched_queries: list[str] = []


class Evidence(BaseModel):
    url: str
    quote: str = Field(description="Short verbatim excerpt from the source that supports the verdict.")


Status = Literal["met", "not_met", "unclear", "skipped", "error"]


class Verdict(BaseModel):
    criterion_id: str
    status: Status
    confidence: float = 0.0
    reasoning: str = ""
    evidence: list[Evidence] = []
    tool_calls: int = 0
    revisions: int = 0  # times the verdict was sent back for breaking a submission rule


class Contact(BaseModel):
    linkedin_url: str | None = None
    email: str | None = None
    email_source: str | None = None  # page the email was found on, when Exa returns a citation
    email_status: Literal["found", "not_found", "not_requested", "error"] = "not_requested"


class CandidateReport(BaseModel):
    candidate: Candidate
    verdicts: list[Verdict]
    qualified: bool
    score: float
    contact: Contact = Contact()


class RunReport(BaseModel):
    query: str
    plan: SearchPlan
    results: list[CandidateReport]
    email_lookup_cost: float | None = None
