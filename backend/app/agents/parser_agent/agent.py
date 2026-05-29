import os
import sys
import json
import re
import requests
from typing import Optional, List
from pathlib import Path

# Add the app directory to the path to import models
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from models import UserQuery, ParsedResume 

class Parser: 
    def __init__(self, query: UserQuery): 
        self.query = query
        self.ollama_base_url = os.environ.get("OLLAMA_BASE_URL", os.environ.get("OLLAMA_URL", "http://localhost:11434"))
        self.model_name = self._get_available_model()
    
    def _get_available_model(self) -> str:
        """
        Check locally available Ollama models and return the best available one.
        Falls back to a default model name if connection fails.
        """
        try:
            response = requests.get(f"{self.ollama_base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models_data = response.json()
                available_models = [model["name"].split(":")[0] for model in models_data.get("models", [])]
                
                # Prioritize models based on capability for parsing tasks
                preferred_models = ["mistral", "neural-chat", "llama2", "orca", "openhermes"]
                for preferred in preferred_models:
                    for model in available_models:
                        if preferred in model.lower():
                            print(f"Using Ollama model: {model}")
                            return model
                
                # If any model exists, use the first one
                if available_models:
                    print(f"Using Ollama model: {available_models[0]}")
                    return available_models[0]
        except (requests.exceptions.RequestException, Exception) as e:
            print(f"Warning: Could not connect to Ollama at {self.ollama_base_url}: {str(e)}")
            print("Using default model name: mistral")
        
        return "mistral"
    
    def parse(self) -> ParsedResume:
        """
        Parse raw resume text and extract structured information.
        Uses local Ollama model to intelligently extract resume details.
        """
        prompt = self._build_parsing_prompt()
        
        try:
            # Call Ollama API
            response = requests.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.3,  # Lower temperature for more structured output
                },
                timeout=60
            )
            
            if response.status_code != 200:
                raise Exception(f"Ollama API error: {response.status_code} - {response.text}")
            
            response_data = response.json()
            response_text = response_data.get("response", "")
        except requests.exceptions.ConnectionError:
            print(f"Error: Cannot connect to Ollama at {self.ollama_base_url}")
            print("Make sure Ollama is running: ollama serve")
            raise
        except Exception as e:
            print(f"Error calling Ollama API: {str(e)}")
            raise
        
        # Parse the JSON response
        parsed_data = self._extract_json_from_response(response_text)
        
        # Create and return ParsedResume object
        return ParsedResume(
            name=parsed_data.get("name", ""),
            email=parsed_data.get("email"),
            current_title=parsed_data.get("current_title"),
            total_years_experience=float(parsed_data.get("total_years_experience", 0)),
            core_skills=parsed_data.get("core_skills", []),
            experience_highlights=parsed_data.get("experience_highlights", [])
        )
    
    
    def _build_parsing_prompt(self) -> str:
        """
        Build the prompt for Ollama to parse the resume.
        Returns a JSON-formatted response.
        """
        prompt = f"""You are a professional resume parser. Analyze the following resume text and extract key information.

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
        
        return prompt
    
    def _extract_json_from_response(self, response: str) -> dict:
        """
        Extract JSON data from the Ollama response.
        Handles cases where JSON might be wrapped in markdown code blocks.
        """
        # Try to find JSON in code blocks first
        json_match = re.search(r'```(?:json)?\s*({.*?})\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find JSON object directly
            json_match = re.search(r'{.*}', response, re.DOTALL)
            json_str = json_match.group(0) if json_match else response
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # If JSON parsing fails, return a default structure
            return {
                "name": "",
                "email": None,
                "current_title": None,
                "total_years_experience": 0,
                "core_skills": [],
                "experience_highlights": []
            }


