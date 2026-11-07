import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0",
                port=int(os.getenv("PORT", "12000")), reload=False)
