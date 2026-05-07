@echo off
cd /d "C:\Users\shaur\OneDrive\Desktop\Vault\Code\philosopher-pipeline"
echo [%date% %time%] Pipeline started >> logs\pipeline.log
"C:\Users\shaur\AppData\Local\Programs\Python\Python312\python.exe" pipeline.py --now >> logs\pipeline.log 2>&1
echo [%date% %time%] Pipeline finished >> logs\pipeline.log
