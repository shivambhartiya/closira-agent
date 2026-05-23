# Closira AI Agent - Bloom Aesthetics Clinic

A Python CLI application demonstrating a 4-stage AI customer support workflow for Closira. It can run with OpenAI, Anthropic, or any OpenAI-compatible hosted model provider such as Hugging Face Inference Providers, OpenRouter, Together, Fireworks, Groq, or a hosted Qwen endpoint.

## What It Does

The agent handles a full customer conversation across four stages:

1. **FAQ Answering** - Answers only from the clinic SOP in `data/sop.json`.
2. **Lead Qualification** - Asks structured questions for business type, team size, and current tools.
3. **Escalation Detection** - Hands off for complaints, angry sentiment, medical questions, pricing negotiation, explicit human requests, low confidence, and repeated SOP gaps.
4. **Conversation Summary** - Generates a structured end-of-session summary and saves a JSON log.

## Setup

**Requirements:** Python 3.9+

```bash
cd closira-agent
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` for your provider.

## Provider Config

Use one of these options without changing code.

### Hugging Face / Qwen / OpenAI-Compatible

```env
LLM_PROVIDER=openai_compatible
LLM_API_KEY=your_provider_api_key_here
LLM_MODEL=Qwen/Qwen2.5-72B-Instruct
LLM_BASE_URL=https://router.huggingface.co/v1
```

This mode also works for providers that expose an OpenAI-compatible `/v1/chat/completions` API. Change `LLM_BASE_URL` and `LLM_MODEL` to match the provider.

### OpenAI

```env
LLM_PROVIDER=openai
LLM_API_KEY=your_openai_api_key_here
LLM_MODEL=gpt-4.1-mini
```

### Groq / Llama

```env
LLM_PROVIDER=openai_compatible
LLM_API_KEY=your_groq_api_key_here
LLM_MODEL=llama-3.1-8b-instant
LLM_BASE_URL=https://api.groq.com/openai/v1
```

Groq keys usually start with `gsk_`. If you accidentally paste one into a chat, rotate it in the Groq console and use the new key in `.env`.

### Anthropic

```env
LLM_PROVIDER=anthropic
LLM_API_KEY=your_anthropic_api_key_here
LLM_MODEL=claude-sonnet-4-20250514
```

Legacy variables such as `OPENAI_API_KEY`, `OPENAI_MODEL`, `ANTHROPIC_API_KEY`, and `ANTHROPIC_MODEL` are also supported, but the provider-neutral `LLM_*` variables are recommended.

## Running

```bash
python main.py
```

On Windows, if `python` is not on PATH:

```powershell
py -3 main.py
```

Type `bye`, `quit`, or `done` at any time to end the session and generate a summary.

## Test Transcript Scenarios

After your provider key and credits are active, run `python main.py` and capture these conversations:

| File | Customer flow |
|---|---|
| `01_in_scope_question.md` | `What are your Botox prices?` then `bye` |
| `02_out_of_scope_question.md` | Ask `Do you offer laser hair removal?`, then `Do you have parking?`; escalation fires at the second SOP gap |
| `03_escalation_trigger.md` | `i had your previous service it was pathetic` |
| `04_lead_qualification.md` | Ask three FAQ questions, ask a pricing question during qualification, then answer the qualification prompts one at a time |
| `05_conversation_summary.md` | Complete three FAQ exchanges, answer all qualification prompts, then type `bye` |

Do not commit `.env` or generated `logs/*.json`; both are ignored by `.gitignore`.

## Project Structure

| Path | Purpose |
|---|---|
| `main.py` | CLI entry point and conversation loop |
| `agent/stages.py` | FAQ and qualification stage handlers |
| `agent/escalation.py` | Provider adapter, escalation pre-filter, trigger logic, logging |
| `agent/summariser.py` | Session summary generator and log writer |
| `agent/sop.py` | SOP loader and text formatter |
| `agent/state.py` | ConversationState dataclass |
| `data/sop.json` | Clinic SOP data |
| `logs/` | Runtime session and escalation logs |
| `test_transcripts/` | Sample conversations for each expected behaviour |
| `prompt_design.md` | Full prompt documentation and design decisions |
| `.gitignore` | Prevents local secrets, cache files, and runtime JSON logs from being committed |

## Safety and Escalation

- The SOP is injected into every model call.
- Every model call requests JSON output through the central `call_llm()` helper.
- The app tracks `can_answer`, `sop_gap`, `confidence`, and `escalate` fields.
- Two consecutive SOP gaps force escalation in application code.
- Escalations are logged immediately to `logs/escalation_{session_id}.json`.

## Known Limitations

- Stateless between sessions; no CRM or persistent customer profile.
- SOP is static JSON; production would use a CMS or database.
- Qualification questions are fixed rather than adaptive.
- API errors are handled safely, but production should add retry/backoff.
- CLI prototype only; no WhatsApp, email, or phone webhook integration.

See `prompt_design.md` for full design reasoning.
