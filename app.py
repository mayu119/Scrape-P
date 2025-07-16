from scrape_web_app import app

# Vercel用のエントリーポイント
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)