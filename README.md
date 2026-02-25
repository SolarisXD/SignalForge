# SignalForge

SignalForge is a local-first LinkedIn content automation system.

## Features
- Generates structured LinkedIn posts using a local LLM (Ollama)
- Rotates topics intelligently, avoiding repetition
- Saves drafts to Notion with metadata
- Runs autonomously via Windows Task Scheduler every 3 days

## Setup
1. Install Python 3.10+
2. Install dependencies: `pip install -r requirements.txt`
3. Configure `config.env` with your Notion token and database ID
4. Set up Windows Task Scheduler to run `linkedin_automation.py` every 3 days


## Windows Task Scheduler Setup

To automate SignalForge every 3 days:

1. Open Task Scheduler (Windows).
2. Create a new task:
	 - Trigger: Daily, repeat every 3 days.
	 - Action: Start a program
		 - Program/script: `python`
		 - Add arguments: `linkedin_automation.py`
		 - Start in: Full path to the `signalforge` directory
	 - Set to run whether user is logged in or not.
	 - Ensure environment variables (NOTION_TOKEN, etc.) are available to the task.
3. Save and enable the task.

No user interaction is required after setup.

## Configuration
Edit `config.env` for model, topic history path, and word limit.

## Security
Store your Notion token in the environment or `config.env`. Never commit secrets to version control.

## License
MIT
