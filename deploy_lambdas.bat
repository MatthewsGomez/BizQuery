@echo off
setlocal EnableDelayedExpansion

REM ============================================================
REM BizQuery - Script de despliegue de Lambdas
REM ============================================================

set ROLE_ARN=arn:aws:iam::985124893674:role/bizquery-lambda-role
set REGION=us-west-2
set DB_HOST=bizquery-db.cf80m82eqktb.us-west-2.rds.amazonaws.com
set DB_NAME=bizquery
set DB_USER=bizquery_user
set DB_PASSWORD=BizQuery2024!
set DB_PORT=5432
set DB_SSLMODE=require

set "BASE_DIR=%~dp0"
set "LAMBDA_DIR=%BASE_DIR%lambda"
set "SHARED_DIR=%LAMBDA_DIR%\shared"
set "VENV=%BASE_DIR%venv"

REM ============================================================
REM  Activar venv
REM ============================================================
echo.
echo Activando venv...
if not exist "%VENV%\Scripts\activate.bat" (
    echo [ERROR] No se encontro el venv en: "%VENV%"
    pause & exit /b 1
)
call "%VENV%\Scripts\activate.bat"
echo venv activado OK

echo.
echo ============================================================
echo  Limpiando paquetes anteriores...
echo ============================================================
if exist "%BASE_DIR%query_sales.zip"       del "%BASE_DIR%query_sales.zip"
if exist "%BASE_DIR%query_inventory.zip"   del "%BASE_DIR%query_inventory.zip"
if exist "%BASE_DIR%analyze_discounts.zip" del "%BASE_DIR%analyze_discounts.zip"
if exist "%LAMBDA_DIR%\query_sales\package"       rmdir /s /q "%LAMBDA_DIR%\query_sales\package"
if exist "%LAMBDA_DIR%\query_inventory\package"   rmdir /s /q "%LAMBDA_DIR%\query_inventory\package"
if exist "%LAMBDA_DIR%\analyze_discounts\package" rmdir /s /q "%LAMBDA_DIR%\analyze_discounts\package"

echo.
echo ============================================================
echo  Empaquetando query_sales...
echo ============================================================
mkdir "%LAMBDA_DIR%\query_sales\package"

pip install psycopg2-binary ^
    --platform manylinux2014_x86_64 ^
    --python-version 3.12 ^
    --only-binary=:all: ^
    -t "%LAMBDA_DIR%\query_sales\package" -q

if exist "%LAMBDA_DIR%\query_sales\requirements.txt" (
    pip install -r "%LAMBDA_DIR%\query_sales\requirements.txt" ^
        --platform manylinux2014_x86_64 ^
        --python-version 3.12 ^
        --only-binary=:all: ^
        -t "%LAMBDA_DIR%\query_sales\package" -q
)

xcopy "%SHARED_DIR%" "%LAMBDA_DIR%\query_sales\package\shared\" /E /I /Q /Y
copy "%LAMBDA_DIR%\query_sales\handler.py"  "%LAMBDA_DIR%\query_sales\package\" /Y
copy "%LAMBDA_DIR%\query_sales\models.py"   "%LAMBDA_DIR%\query_sales\package\" /Y
copy "%LAMBDA_DIR%\query_sales\queries.py"  "%LAMBDA_DIR%\query_sales\package\" /Y
copy "%LAMBDA_DIR%\query_sales\__init__.py" "%LAMBDA_DIR%\query_sales\package\" /Y

powershell -Command "Compress-Archive -Path '%LAMBDA_DIR%\query_sales\package\*' -DestinationPath '%BASE_DIR%query_sales.zip' -Force"
echo query_sales.zip creado OK

echo.
echo ============================================================
echo  Empaquetando query_inventory...
echo ============================================================
mkdir "%LAMBDA_DIR%\query_inventory\package"

pip install psycopg2-binary ^
    --platform manylinux2014_x86_64 ^
    --python-version 3.12 ^
    --only-binary=:all: ^
    -t "%LAMBDA_DIR%\query_inventory\package" -q

if exist "%LAMBDA_DIR%\query_inventory\requirements.txt" (
    pip install -r "%LAMBDA_DIR%\query_inventory\requirements.txt" ^
        --platform manylinux2014_x86_64 ^
        --python-version 3.12 ^
        --only-binary=:all: ^
        -t "%LAMBDA_DIR%\query_inventory\package" -q
)

xcopy "%SHARED_DIR%" "%LAMBDA_DIR%\query_inventory\package\shared\" /E /I /Q /Y
copy "%LAMBDA_DIR%\query_inventory\handler.py"  "%LAMBDA_DIR%\query_inventory\package\" /Y
copy "%LAMBDA_DIR%\query_inventory\models.py"   "%LAMBDA_DIR%\query_inventory\package\" /Y
copy "%LAMBDA_DIR%\query_inventory\queries.py"  "%LAMBDA_DIR%\query_inventory\package\" /Y
copy "%LAMBDA_DIR%\query_inventory\__init__.py" "%LAMBDA_DIR%\query_inventory\package\" /Y

powershell -Command "Compress-Archive -Path '%LAMBDA_DIR%\query_inventory\package\*' -DestinationPath '%BASE_DIR%query_inventory.zip' -Force"
echo query_inventory.zip creado OK

echo.
echo ============================================================
echo  Empaquetando analyze_discounts...
echo ============================================================
mkdir "%LAMBDA_DIR%\analyze_discounts\package"

pip install psycopg2-binary ^
    --platform manylinux2014_x86_64 ^
    --python-version 3.12 ^
    --only-binary=:all: ^
    -t "%LAMBDA_DIR%\analyze_discounts\package" -q

if exist "%LAMBDA_DIR%\analyze_discounts\requirements.txt" (
    pip install -r "%LAMBDA_DIR%\analyze_discounts\requirements.txt" ^
        --platform manylinux2014_x86_64 ^
        --python-version 3.12 ^
        --only-binary=:all: ^
        -t "%LAMBDA_DIR%\analyze_discounts\package" -q
)

xcopy "%SHARED_DIR%" "%LAMBDA_DIR%\analyze_discounts\package\shared\" /E /I /Q /Y
copy "%LAMBDA_DIR%\analyze_discounts\handler.py"   "%LAMBDA_DIR%\analyze_discounts\package\" /Y
copy "%LAMBDA_DIR%\analyze_discounts\models.py"    "%LAMBDA_DIR%\analyze_discounts\package\" /Y
copy "%LAMBDA_DIR%\analyze_discounts\queries.py"   "%LAMBDA_DIR%\analyze_discounts\package\" /Y
copy "%LAMBDA_DIR%\analyze_discounts\analyzer.py"  "%LAMBDA_DIR%\analyze_discounts\package\" /Y
copy "%LAMBDA_DIR%\analyze_discounts\__init__.py"  "%LAMBDA_DIR%\analyze_discounts\package\" /Y

powershell -Command "Compress-Archive -Path '%LAMBDA_DIR%\analyze_discounts\package\*' -DestinationPath '%BASE_DIR%analyze_discounts.zip' -Force"
echo analyze_discounts.zip creado OK

echo.
echo ============================================================
echo  Desplegando Lambdas en AWS...
echo ============================================================

set "ZIP_SALES=%BASE_DIR%query_sales.zip"
set "ZIP_INVENTORY=%BASE_DIR%query_inventory.zip"
set "ZIP_DISCOUNTS=%BASE_DIR%analyze_discounts.zip"
set ENV_VARS=Variables={DB_HOST=%DB_HOST%,DB_NAME=%DB_NAME%,DB_USER=%DB_USER%,DB_PASSWORD=%DB_PASSWORD%,DB_PORT=%DB_PORT%,DB_SSLMODE=%DB_SSLMODE%}

REM --- query_sales ---
echo Desplegando bizquery-query-sales...
aws lambda create-function --function-name bizquery-query-sales --runtime python3.12 --role %ROLE_ARN% --handler handler.handler --zip-file "fileb://%ZIP_SALES%" --timeout 30 --memory-size 256 --region %REGION% --environment "%ENV_VARS%" --query "FunctionArn" --output text 2>nul
IF %ERRORLEVEL% NEQ 0 (
    echo Actualizando bizquery-query-sales existente...
    aws lambda update-function-code --function-name bizquery-query-sales --zip-file "fileb://%ZIP_SALES%" --region %REGION% --query "FunctionArn" --output text
    aws lambda update-function-configuration --function-name bizquery-query-sales --environment "%ENV_VARS%" --region %REGION% >nul
)

REM --- query_inventory ---
echo Desplegando bizquery-query-inventory...
aws lambda create-function --function-name bizquery-query-inventory --runtime python3.12 --role %ROLE_ARN% --handler handler.handler --zip-file "fileb://%ZIP_INVENTORY%" --timeout 30 --memory-size 256 --region %REGION% --environment "%ENV_VARS%" --query "FunctionArn" --output text 2>nul
IF %ERRORLEVEL% NEQ 0 (
    echo Actualizando bizquery-query-inventory existente...
    aws lambda update-function-code --function-name bizquery-query-inventory --zip-file "fileb://%ZIP_INVENTORY%" --region %REGION% --query "FunctionArn" --output text
    aws lambda update-function-configuration --function-name bizquery-query-inventory --environment "%ENV_VARS%" --region %REGION% >nul
)

REM --- analyze_discounts ---
echo Desplegando bizquery-analyze-discounts...
aws lambda create-function --function-name bizquery-analyze-discounts --runtime python3.12 --role %ROLE_ARN% --handler handler.handler --zip-file "fileb://%ZIP_DISCOUNTS%" --timeout 30 --memory-size 256 --region %REGION% --environment "%ENV_VARS%" --query "FunctionArn" --output text 2>nul
IF %ERRORLEVEL% NEQ 0 (
    echo Actualizando bizquery-analyze-discounts existente...
    aws lambda update-function-code --function-name bizquery-analyze-discounts --zip-file "fileb://%ZIP_DISCOUNTS%" --region %REGION% --query "FunctionArn" --output text
    aws lambda update-function-configuration --function-name bizquery-analyze-discounts --environment "%ENV_VARS%" --region %REGION% >nul
)

echo.
echo ============================================================
echo  Verificando Lambdas desplegadas...
echo ============================================================
aws lambda list-functions --region %REGION% --query "Functions[?starts_with(FunctionName, 'bizquery')].FunctionName" --output table

echo.
echo ============================================================
echo  Despliegue completado!
echo ============================================================

pause
endlocal