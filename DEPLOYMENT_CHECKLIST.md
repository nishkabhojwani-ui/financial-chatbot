# Deployment Checklist

## Before Deploying ✅

- [ ] Have a GitHub account (create at github.com if needed)
- [ ] Have an OpenRouter API key (from openrouter.ai)
- [ ] Have the database file `financial_data.db` in the project folder
- [ ] All files listed below exist in your project:

```
Financial_chatbot_dp_world/
├── streamlit_app.py          ✅ Main app
├── financial_data.db         ✅ Database (CRITICAL!)
├── requirements.txt          ✅ Dependencies
├── .streamlit/
│   └── config.toml          ✅ Streamlit config
├── .gitignore               ✅ Git ignore rules
├── DEPLOYMENT_GUIDE.md      ✅ This guide
└── README.md                (optional but recommended)
```

## Deploy in 5 Steps

### 1. Create GitHub Repository
```bash
cd c:\Users\NISHKA\Downloads\Financial_chatbot_dp_world
git init
git config user.name "Your Name"
git config user.email "your@email.com"
git add .
git commit -m "Initial commit: DP World FP&A Chatbot"
```

### 2. Push to GitHub
- Go to github.com
- Create new repo called `financial-chatbot`
- Copy the git remote URL
- Run:
```bash
git remote add origin https://github.com/YOUR_USERNAME/financial-chatbot.git
git branch -M main
git push -u origin main
```

### 3. Go to Streamlit Cloud
- Visit https://streamlit.io/cloud
- Click "Sign in with GitHub"
- Click "Deploy an app"
- Select your repo and `streamlit_app.py`
- Click "Deploy"

### 4. Add API Key Secret
- Wait for deployment to complete (~2 minutes)
- Click **menu (⋮)** → **Settings**
- Click **Secrets**
- Add:
```
OPENROUTER_API_KEY=your_key_here
```
- Save

### 5. Test
- App auto-reloads
- Try asking: "EBITDA for Africa and MENA"
- Should return results!

## After Deployment ✅

- [ ] Test the app at your Streamlit URL
- [ ] Share link with team
- [ ] Monitor OpenRouter API usage
- [ ] Check logs if issues occur

## Useful Links

| What | Link |
|------|------|
| Streamlit Cloud | https://streamlit.io/cloud |
| GitHub | https://github.com |
| OpenRouter Dashboard | https://openrouter.ai/account/usage |
| Streamlit Docs | https://docs.streamlit.io |

## Support

If you get stuck:
1. Read `DEPLOYMENT_GUIDE.md` in detail
2. Check Streamlit Cloud logs (click menu → Manage app)
3. Verify `financial_data.db` is in GitHub repo
4. Check OpenRouter API key is correctly added to Secrets

---

**You're ready to deploy! 🚀**
