#### Getting start
1. Создать папку *custom_python_modules* рядом с папкой проекта, которому требуются модули  
2. В созданной папке бахаем `git clone <..>`  
3. Переходим в папку проекта, для которого устанавливаются *custom_python_modules*
4. Проверяем что *requirements* проекта содержит: `-e ../custom_python_modules`  
5. На Windows выполняем в CMD (не PS!)
```
py -V:3.12 -m venv venv       # Создаем виртуальное окружение
venv\Scripts\activate.bat       # Проваливаемся в окружение (bat для windows, без bat - для linux)
pip install -r requirements.txt # Устанавливаем библиотеки
```  
6. Для запуска скрипта, в том числе из планировщика задач, используем `start.bat`. По умолчанию батник предполагает, что запускаемый скрипт - это `main.py`, а папка с окружением - `venv`. При необходимости внеси изменения в строку 10 и 35.
<br>  

#### Updating  
1. Выполняем `git pull` в папке *custom_python_modules*  
2. Повторяем `pip install -r requirements.txt` в окружении каждого проекта
<br>

#### Список требуемых переменных окружения для работы модулей:
- **netbox_connector**: `NETBOX_URL`, `NETBOX_TOKEN`
- **prtg_connector**: `PRTG_URL`, `PRTG_API_TOKEN`, `PRTG_VERIFY_SSL`
- **pfsense**: `PFSENSE_LOGIN`, `PFSENSE_PASSWORD`
- **gitlab_connector**: `GITLAB_URL`, `GITLAB_PRIVATE_TOKEN`