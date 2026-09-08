Frontend (React + Vite) scaffold

Quick start:

1. cd frontend
2. npm install
3. npm run dev

The frontend expects the backend API to be available at http://localhost:8000/api/signals.
During development you can run the backend with:

```bash
cd backend
python -m pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

When the backend is running, the frontend will fetch signals and render them.
