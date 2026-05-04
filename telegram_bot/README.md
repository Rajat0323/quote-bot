# Telegram Content Bot

A lightweight Python bot that can either fetch live news for exam-focused current-affairs posts or read local book documents, turn them into motivational quote posts with an LLM, and publish everything to Telegram.

## What it does

- Supports two content modes:
  - `news`: live current-affairs posts with summaries, relevance points, and MCQs
  - `books`: motivational quote posts generated from local `.txt`, `.md`, `.docx`, or `.json` book files
- Pulls the latest articles using multiple providers with fallback when `CONTENT_MODE=news`:
  - `newsdata.io` India-focused query first
  - `newsdata.io` worldwide query second
  - `NewsAPI` worldwide query as an additional fallback
- Reads book documents from `data/books` when `CONTENT_MODE=books`, splits them into LLM-sized excerpts, and avoids reposting the same excerpt twice.
- Uses an OpenAI-compatible LLM API to create:
  - current-affairs summaries and MCQs in `news` mode
  - motivational quote posts, takeaways, and hashtags in `books` mode
- Posts channel-ready content with a branded footer, join prompts, searchable hashtags, and an optional SEO-style channel description update.
- Posts to a Telegram channel and optionally a Telegram group.
- Keeps channel and group content different:
  - channel gets the polished main post
  - group gets discussion starters, quiz prompts, polls, and delayed answer reveals when MCQs exist
- Stores posted item ids in `data/posted_articles.json` to avoid reposting.
- Includes a GitHub Actions workflow for scheduled runs.

## Project structure

```text
telegram_bot/
|-- current_affairs_bot/
|   |-- __init__.py
|   |-- config.py
|   |-- document_client.py
|   |-- llm_client.py
|   |-- models.py
|   |-- news_client.py
|   |-- service.py
|   |-- state_store.py
|   `-- telegram_client.py
|-- data/
|   |-- books/
|   `-- posted_articles.json
|-- .env.example
|-- main.py
|-- README.md
`-- requirements.txt
```

## Local setup

1. Create a Telegram bot with BotFather.
2. Add the bot as an admin in your channel and, if needed, in your group.
3. Copy `.env.example` to `.env` and fill in your keys.
4. If you want motivational quote posts, set `CONTENT_MODE=books` and place your source files in `data/books`.
5. Install dependencies:

```bash
cd telegram_bot
pip install -r requirements.txt
```

## Local run

Run one cycle:

```bash
python main.py --once
```

Preview content without posting to Telegram:

```bash
python main.py --once --dry-run
```

Run continuously with polling:

```bash
python main.py
```

## Books mode

Use `CONTENT_MODE=books` to generate motivational Telegram posts from your own documents.

- Put `.txt`, `.md`, `.docx`, or `.json` files inside [telegram_bot/data/books](/C:/Users/Rajat%20Gupta/Documents/New%20project%203/telegram_bot/data/books).
- The bot reads each file, creates excerpt chunks, sends those excerpts to the LLM, and posts one fresh excerpt at a time.
- `TELEGRAM_CHANNEL_DESCRIPTION` lets the bot update the channel description with SEO-friendly keywords when the bot has admin rights.
- The default books-mode call to action, hashtags, and brand text can all be overridden through `.env`.

Recommended books-mode settings:

```env
CONTENT_MODE=books
TELEGRAM_BRAND_NAME=Quote Bot Daily
TELEGRAM_CALL_TO_ACTION=Join for daily motivational quotes from books, mindset lessons, and shareable self-growth posts.
TELEGRAM_CHANNEL_DESCRIPTION=Daily motivational quotes from books, mindset lessons, self growth insights, and shareable inspiration posts.
TELEGRAM_DISCOVERY_KEYWORDS=motivational quotes, book quotes, self growth, mindset motivation, daily inspiration, success habits
BOOKS_SOURCE_DIR=data/books
```

## GitHub Actions

The workflow file is:

```text
.github/workflows/current-affairs-bot.yml
```

The workflow now loads non-secret runtime settings from [telegram_bot/github-actions.env](/C:/Users/Rajat%20Gupta/Documents/New%20project%203/telegram_bot/github-actions.env). Keep only tokens and API keys in GitHub Secrets.

It supports:

- scheduled runs every 15 minutes
- manual runs from the Actions tab
- committing `telegram_bot/data/posted_articles.json` back to the repo so posted-news state survives across runs

### Required repository secrets

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHANNEL_ID`
- `OPENAI_API_KEY`

### Optional repository secrets

- `NEWS_API_KEY`
- `NEWSDATA_API_KEY`
- `TELEGRAM_GROUP_ID`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`

Set at least one of `NEWS_API_KEY` or `NEWSDATA_API_KEY` only when `CONTENT_MODE=news`.

### Repository config file

Store non-secret GitHub Actions settings in:

```text
telegram_bot/github-actions.env
```

### Group behavior

- The channel keeps the current full-post format for the active mode.
- The group does not receive the same summary post.
- `TELEGRAM_GROUP_REF` is only for public discovery/footer text.
- Actual group posting always requires `TELEGRAM_GROUP_ID`.
- If Telegram upgrades a group to a supergroup, it returns a replacement chat id. The bot now retries automatically for that run, but you should still update `TELEGRAM_GROUP_ID` in your secrets or `.env`.
- For each fresh article, the group now gets:
  - 1 discussion starter
  - 1 quiz prompt per MCQ
  - 1 delayed answer reveal per MCQ in a later cycle
- Every group message includes hashtags and the channel reference when `TELEGRAM_CHANNEL_REF` is set.
- Pending answer reveals are stored in `data/pending_group_reveals.json`.

If `OPENAI_MODEL` is not set, the bot defaults to `gpt-4.1-mini`.

## Notes

- This project uses direct Telegram Bot API calls, so there is no heavy Telegram framework to maintain.
- "Real time" here means scheduled polling. Adjust the GitHub Actions cron or local run mode as needed.
- The default news query is broad. You should tune it further for polity, economy, science-tech, international relations, environment, and sports.
- For books mode, convert PDFs to `.txt`, `.md`, `.docx`, or `.json` before adding them to `data/books`.
- Telegram discovery is influenced by public username, channel/group title, description, post consistency, and engagement. This bot can improve post wording and keyword coverage, but it cannot bypass anti-spam bans from mass-sharing links in unrelated groups.

