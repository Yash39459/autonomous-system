run following commands

python -m venv venv

pip install python-dotenv

pip install -r requirements.txt

uvicorn main:app --reload --env-file .env

