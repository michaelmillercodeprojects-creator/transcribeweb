# Deploy to Render

1. Go to [render.com](https://render.com) and sign up
2. Click "New" → "Web Service" 
3. Connect your GitHub repo: `transcribeweb`
4. Render will auto-detect the config
5. Add environment variable: `OPENAI_API_KEY` = your OpenAI key
6. Click "Create Web Service"
7. Wait 5 minutes for deployment

Your app will be live at: `https://transcribeweb.onrender.com`