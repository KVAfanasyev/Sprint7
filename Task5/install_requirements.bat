@echo off
echo Install dependencies for bot...

pip install --upgrade pip
pip install python-telegram-bot>=20.0
pip install chromadb>=0.4.0
pip install sentence-transformers>=2.2.0
pip install scipy>=1.10.0 --prefer-binary

echo All dependencies are installed!
pause