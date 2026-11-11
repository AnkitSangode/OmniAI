
# OmniAI

OmniAI is a unified multimodal AI platform that provides text, image, audio, and video AI capabilities through a single application.

## Tech Stack

### Frontend
- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui

### Backend
- FastAPI
- Python
- PostgreSQL
- SQLAlchemy
- Alembic
- JWT Authentication

### AI Infrastructure
- LiteLLM
- Diffusers / ComfyUI
- Whisper
- XTTS
- Llama Guard
- Langfuse

## Project Structure

```text
omniai/
├── backend/
├── frontend/
├── docs/
├── .gitignore
└── README.md
```

## Features

- User registration and authentication
- Text AI
- Image generation
- Speech-to-text
- Text-to-speech
- Video processing
- AI safety and moderation
- Usage analytics and cost tracking

## Development Status

- [x] Project foundation
- [x] User authentication
- [ ] Text AI integration
- [ ] Image AI integration
- [ ] Audio AI integration
- [ ] Video AI integration
- [ ] Safety and governance
- [ ] Analytics and monitoring
- [ ] Deployment

## Local Development

See the backend and frontend setup instructions in their respective directories.

## License

To be determined.
```

This README will evolve as we implement the remaining features.

## Step 5 – Initialize Git locally

First, make sure you're in the root directory:

```powershell
cd "D:\Internship projects\New folder\omniai"
```

Check whether Git has already been initialized:

```powershell
Test-Path .git
```

If it returns `False`, initialize the repository:

```powershell
git init
```

Set the main branch:

```powershell
git branch -M main
```

Check Git:

```powershell
git status
```

You should see your project files listed as untracked.

## Step 6 – Configure your Git identity

If this is your first Git setup, configure your name and email.

Use the same email associated with your GitHub account if you want your commits associated with your profile.

```powershell
git config --global user.name "Your GitHub Name"
git config --global user.email "your-email@example.com"
```

Verify:

```powershell
git config --global --list
```

## Step 7 – Verify that secrets are protected

Before uploading anything, run:

```powershell
git check-ignore backend/.env
git check-ignore frontend/.env.local
```

Both commands should return the corresponding file paths.

Also inspect the pending files:

```powershell
git status --short
```

<badge color="danger">Important</badge> Never upload `.env`, `.env.local`, API keys, database passwords, JWT secrets, or private credentials.

We'll create safe `.env.example` files separately, containing variable names and placeholder values only.

## Step 8 – Create your GitHub repository

Open:

<Link url="https://github.com/new" title="Create a new GitHub repository"/>

<AsyncImage query="GitHub create a new repository page owner repository name description public private initialize README interface" aspectRatio="16:9" width="100%"/>

Use these settings:

| Setting | Value |
|---|---|
| Repository name | `OmniAI` |
| Description | Unified Multimodal AI Platform |
| Visibility | Public (recommended for portfolio) |
| Add README | Do not select |
| Add .gitignore | None |
| License | None for now |

Click **Create repository**.

We are not selecting README or `.gitignore` because we've already created those files locally.

## Step 9 – Connect your local project to GitHub

GitHub will show you a repository URL.

It will look like:

```text
https://github.com/YOUR_USERNAME/OmniAI.git
```

Copy your actual URL and run:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/OmniAI.git
```

Verify:

```powershell
git remote -v
```

You should see your GitHub repository URL.

## Step 10 – Make your first commit

Stage the files:

```powershell
git add .
```

Inspect what will be committed:

```powershell
git status
```

Make sure no secrets, `.env` files, `node_modules`, `.next`, or virtual environments are included.

Then commit:

```powershell
git commit -m "chore: initialize OmniAI monorepo with Day 1 foundation"
```

Push to GitHub:

```powershell
git push -u origin main
```

Your project should now appear on GitHub.

---

## Our Git workflow from now on

Every meaningful feature will have its own commit.

For example:

| Milestone | Commit message |
|---|---|
| Initial foundation | `chore: initialize OmniAI monorepo` |
| Authentication | `feat: implement JWT authentication` |
| LiteLLM integration | `feat: integrate LiteLLM gateway` |
| Streaming | `feat: implement streaming text generation` |
| Model fallback | `feat: add LLM provider fallback` |
| Usage tracking | `feat: implement user usage tracking` |

## Let's complete this one step at a time

{@body const [step,setStep] = DIL.useState("not-started")}
<box border radius="lg" padding={3} gap={3}>
  **Your current repository setup progress**
  <radio-group direction="col" value={step} onChange={setStep}>
    <radio value="not-started">Haven't started yet</radio>
    <radio value="gitignore">Created `.gitignore` and README</radio>
    <radio value="initialized">Initialized local Git repository</radio>
    <radio value="github">Created empty GitHub repository</radio>
    <radio value="connected">Connected local project to GitHub</radio>
    <radio value="pushed">Successfully pushed to GitHub</radio>
  </radio-group>
  <button block onClick={()=>GenUI.issueNewTurn("My OmniAI GitHub repository setup progress: "+step+". Guide me through the next step.")}>Continue</button>
</box>

**My recommendation:** Don't rush through all ten steps. Complete the initial Git setup and verify that your first push contains the correct files. Then we'll move to Day 2.

