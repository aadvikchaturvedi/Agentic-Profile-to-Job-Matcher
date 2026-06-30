import sys
import json
import re
from typing import Optional
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import requests
from loguru import logger

from models import UserQuery, ParsedResume
from app.core.config import settings
from app.utils.parser_fallback import fallback_parse
from app.utils.json_utils import extract_json_from_response


class Parser:
    def __init__(self, query: UserQuery):
        self.query = query
        self.ollama_base_url = settings.effective_ollama_url
        self.model_name = self._get_available_model()

    def _get_available_model(self) -> str:
        try:
            response = requests.get(f"{self.ollama_base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models_data = response.json()
                available_models = [model["name"].split(":")[0] for model in models_data.get("models", [])]
                preferred_models = ["mistral", "neural-chat", "llama2", "orca", "openhermes"]
                for preferred in preferred_models:
                    for model in available_models:
                        if preferred in model.lower():
                            logger.info("Using Ollama model", model=model)
                            return model
                if available_models:
                    logger.info("Using Ollama model", model=available_models[0])
                    return available_models[0]
        except (requests.exceptions.RequestException, Exception) as e:
            logger.warning("Could not connect to Ollama", error=str(e), url=self.ollama_base_url)

        return "mistral"

    def parse(self) -> ParsedResume:
        prompt = self._build_parsing_prompt()

        try:
            response = requests.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.3,
                },
                timeout=60,
            )

            if response.status_code != 200:
                raise Exception(f"Ollama API error: {response.status_code} - {response.text}")

            response_data = response.json()
            response_text = response_data.get("response", "")

            parsed_data = self._extract_json_from_response(response_text)
            result = ParsedResume(
                name=parsed_data.get("name", ""),
                email=parsed_data.get("email"),
                current_title=parsed_data.get("current_title"),
                total_years_experience=float(parsed_data.get("total_years_experience", 0)),
                core_skills=parsed_data.get("core_skills", []),
                experience_highlights=parsed_data.get("experience_highlights", []),
            )
            if result.name:
                logger.info("Resume parsed via Ollama", name=result.name)
                return result

        except requests.exceptions.ConnectionError:
            logger.warning("Ollama not reachable, falling back to regex parser")
        except Exception as e:
            logger.warning("Ollama parsing failed, falling back to regex parser", error=str(e))

        # fallback
        fallback = fallback_parse(self.query.raw_job_description)
        if fallback:
            logger.info("Resume parsed via regex fallback", name=fallback.name)
            return fallback

        logger.error("Both Ollama and fallback parser failed, returning empty resume")
        return ParsedResume(
            name="", email=None, current_title=None,
            total_years_experience=0, core_skills=[], experience_highlights=[],
        )

    def _build_parsing_prompt(self) -> str:
        return f"""You are a professional resume parser. Analyze the following resume text and extract key information.

RESUME TEXT:
{self.query.raw_job_description}

Extract and return the following information in JSON format:
{{
    "name": "Full name of the candidate",
    "email": "Email address or null",
    "current_title": "Current job title or most recent title",
    "total_years_experience": 0,
    "core_skills": ["skill1", "skill2", "skill3"],
    "experience_highlights": ["highlight1", "highlight2", "highlight3"]
}}

Instructions:
1. Extract the name from the resume (first and last name)
2. Find and extract the email address if present
3. Identify the current or most recent job title
4. Calculate or estimate total years of professional experience
5. List the top 5-7 core technical and soft skills
6. Provide 3-5 key achievements or highlights from work experience

Return ONLY the JSON object, no additional text."""

    def _extract_json_from_response(self, response: str) -> dict:
        data = extract_json_from_response(response)
        if data is not None:
            return data
        return {
            "name": "",
            "email": None,
            "current_title": None,
            "total_years_experience": 0,
            "core_skills": [],
            "experience_highlights": [],
        }
