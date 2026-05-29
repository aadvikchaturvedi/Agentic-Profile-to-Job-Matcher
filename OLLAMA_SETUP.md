# Ollama Setup Guide for Resume Parser

This guide explains how to set up and use Ollama with the resume parser for local AI-powered resume parsing.

## What is Ollama?

Ollama is a lightweight framework for running large language models locally. It's perfect for:
- Privacy: All data stays on your machine
- Speed: No API latency
- Cost: Free - no API costs
- Control: Use any open-source model

## Installation

### 1. Install Ollama

**macOS:**
```bash
# Download from https://ollama.ai
# Or use Homebrew:
brew install ollama
```

**Linux:**
```bash
curl https://ollama.ai/install.sh | sh
```

**Windows:**
Download from https://ollama.ai/download

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `requests` - For HTTP calls to Ollama
- `pydantic` - For data validation
- `python-dotenv` - For environment variables

## Running Ollama

### Start the Ollama Server

```bash
ollama serve
```

This starts the Ollama server on `http://localhost:11434` (default port).

### Pull a Model

In a new terminal, download a model:

```bash
# Recommended for resume parsing (small and fast)
ollama pull mistral

# Alternative options:
ollama pull neural-chat      # Great for structured output
ollama pull llama2           # General purpose
ollama pull orca             # Good for instructions
```

**Model Sizes:**
- mistral: ~4GB (recommended for most systems)
- neural-chat: ~4GB
- llama2: ~4GB
- orca: ~4GB

### List Available Models

```bash
ollama list
```

## Usage

### Quick Test

```bash
cd backend/app/agents/parser_agent
python main.py
```

This runs the parser with a sample resume using your local Ollama model.

### In Your Code

```python
from agents.parser_agent import Parser
from models import UserQuery

resume_text = "..."  # Your resume text here

query = UserQuery(raw_job_description=resume_text)
parser = Parser(query)
parsed_resume = parser.parse()

print(parsed_resume.name)
print(parsed_resume.core_skills)
print(parsed_resume.total_years_experience)
```

### Configuration

Set environment variables to customize:

```bash
# Use a different Ollama URL
export OLLAMA_BASE_URL=http://192.168.1.100:11434

# Use a specific model
export OLLAMA_MODEL=mistral
```

## How It Works

1. **Model Detection**: Automatically detects available models on your Ollama instance
2. **Resume Parsing**: Sends the resume text to the local model
3. **JSON Extraction**: Parses the structured response
4. **Data Validation**: Validates against Pydantic models

## Troubleshooting

### Error: Cannot connect to Ollama

**Solution**: Make sure Ollama is running:
```bash
ollama serve
```

### Model not found

**Solution**: Pull the model:
```bash
ollama pull mistral
```

### Slow responses

**Solution**: 
- Use a smaller model (mistral is optimized)
- Ensure you have enough RAM
- Increase your system resources

### Out of memory

**Solution**:
- Use a smaller model: `ollama pull orca-mini`
- Close other applications
- Increase available RAM

## Model Recommendations

For resume parsing, we recommend:

1. **mistral** (Best choice)
   - Size: 4GB
   - Speed: Fast
   - Quality: Excellent
   - Command: `ollama pull mistral`

2. **neural-chat**
   - Size: 4GB
   - Speed: Fast
   - Quality: Great for structured output
   - Command: `ollama pull neural-chat`

3. **orca**
   - Size: 4GB
   - Speed: Moderate
   - Quality: Excellent instruction following
   - Command: `ollama pull orca`

## Next Steps

1. Install Ollama
2. Pull a model: `ollama pull mistral`
3. Start Ollama: `ollama serve`
4. Run the parser: `python main.py`
5. Integrate into your application

## Resources

- [Ollama Website](https://ollama.ai)
- [Available Models](https://ollama.ai/library)
- [Documentation](https://github.com/jart/ollama)

## Performance Tips

- Keep Ollama running in the background
- Use mistral for best speed/quality balance
- Monitor system resources (RAM usage)
- Consider using a GPU for faster inference

## Privacy & Security

- All data stays on your local machine
- No external API calls (when using local models)
- No data collection or tracking
- Full control over your models and data
