# DP World FP&A Chatbot - Streamlit Cloud Deployment

## Quick Start (5 minutes)

### Step 1: Prepare Your Files
✅ You already have:
- `streamlit_app.py` - Main application
- `financial_data.db` - SQLite database
- `requirements.txt` - Python dependencies
- `.streamlit/config.toml` - Streamlit configuration

### Step 2: Push to GitHub
```bash
# Initialize git repo (if not already done)
git init
git add .
git commit -m "Add Streamlit chatbot"

# Push to GitHub
git remote add origin https://github.com/YOUR_USERNAME/financial-chatbot
git branch -M main
git push -u origin main
```

### Step 3: Deploy on Streamlit Cloud
1. Go to **https://streamlit.io/cloud**
2. Click **"Sign in with GitHub"** (create account if needed)
3. Click **"Deploy an app"**
4. Select your repo: `financial-chatbot`
5. Set main file: `streamlit_app.py`
6. Click **"Deploy"** ✨

### Step 4: Configure Secrets (API Key)
1. After deployment, click the **three dots menu** → **Settings**
2. Go to **Secrets**
3. Add your OpenRouter API key:
```
OPENROUTER_API_KEY=your_api_key_here
```
4. Save - app will reload automatically

### Done! 🎉
Your chatbot is now live at: `https://streamlit.io/YOUR_APP_NAME`

---

## Alternative: Deploy Locally with Streamlit

If you prefer to test locally first:

```bash
# Install Streamlit
pip install -r requirements.txt

# Run the app
streamlit run streamlit_app.py
```

Then open: `http://localhost:8501`

---

## Troubleshooting

### Issue: "No module named sqlite3"
- Streamlit Cloud includes sqlite3 by default
- If issues occur, it's likely a file path problem
- The database must be in the same directory as `streamlit_app.py`

### Issue: "API key not found"
- Make sure you added it to Streamlit Cloud **Secrets** (not just .env)
- The app needs to restart after adding secrets
- Click the three-dot menu → **Rerun** if it doesn't auto-reload

### Issue: Database not found
- The `financial_data.db` file must be committed to GitHub
- Check it's in your git repo with: `git ls-files | grep financial_data.db`

---

## For Team Access (Optional)

### Using Streamlit Sharing
- Your deployed app is public by default
- To restrict access:
  1. Go to **Settings** → **General**
  2. Change access level (requires Streamlit+ subscription)
  
### Alternative: Company Password
- Add basic auth in the code (contact support for help)

---

## Important Notes

⚠️ **Database Size Limits:**
- Streamlit Cloud free tier supports files up to 200MB
- Your SQLite DB is small, no issue

⚠️ **API Costs:**
- OpenRouter API calls cost money (but very cheap for Haiku model)
- Monitor your usage at https://openrouter.ai

⚠️ **Updates:**
- Changes to GitHub automatically redeploy (within a few minutes)
- No manual redeploy needed

---

## Next Steps

1. **Share the link** with your team
2. **Monitor costs** on OpenRouter dashboard
3. **Collect feedback** and iterate
4. **Scale up** (move to paid Streamlit tier if needed for 24/7 access)

Questions? Check:
- Streamlit Docs: https://docs.streamlit.io
- OpenRouter Docs: https://openrouter.ai/docs
