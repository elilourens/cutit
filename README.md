# cutit

Redact your personal files before they are sent to a cloud api. 

### to run the proxy: 
cd backend
poetry install
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

### to run the realtime viewer
cd frontend 
npm install 
npm run dev