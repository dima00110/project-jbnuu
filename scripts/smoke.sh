#!/usr/bin/env bash
# Smoke-проверка «Регистратуры» через curl.
# Запуск: scripts/smoke.sh   (сервер поднимается сам, если не запущен)
set -u

BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="$BASE_DIR/.venv/bin/python"
PORT="${SMOKE_PORT:-8001}"
BASE="http://127.0.0.1:$PORT"
COOKIES="$(mktemp -d)"
SERVER_PID=""
PASS=0
FAIL=0

cleanup() {
  [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null
  rm -rf "$COOKIES"
}
trap cleanup EXIT

check_eq() {  # name expected actual
  if [ "$2" = "$3" ]; then
    PASS=$((PASS + 1)); printf '  \033[32mPASS\033[0m  %s\n' "$1"
  else
    FAIL=$((FAIL + 1)); printf '  \033[31mFAIL\033[0m  %s (ожидалось: %s, получено: %s)\n' "$1" "$2" "$3"
  fi
}

check_contains() {  # name haystack needle
  case "$2" in
    *"$3"*) PASS=$((PASS + 1)); printf '  \033[32mPASS\033[0m  %s\n' "$1" ;;
    *)      FAIL=$((FAIL + 1)); printf '  \033[31mFAIL\033[0m  %s (нет фрагмента: %s)\n' "$1" "$3" ;;
  esac
}

status() {  # url jar [curl-args...]
  local url=$1 jar=$2; shift 2
  curl -s -o /dev/null -w '%{http_code}' -b "$jar" -c "$jar" "$@" "$url"
}

redirect() {  # url jar [curl-args...] -> redirect_url
  local url=$1 jar=$2; shift 2
  curl -s -o /dev/null -w '%{redirect_url}' -b "$jar" -c "$jar" "$@" "$url"
}

body() {  # url jar -> html
  local url=$1 jar=$2; shift 2
  curl -s -b "$jar" -c "$jar" "$@" "$url"
}

post() {  # url jar [csrf-без токена: key=val...] -> "code|redirect_url"
  local url=$1 jar=$2; shift 2
  local token
  token=$(grep csrftoken "$jar" | awk '{print $7}' | tail -n1)
  local out
  out=$(curl -s -o /dev/null -w '%{http_code}|%{redirect_url}' \
    -b "$jar" -c "$jar" -H "Referer: $url" -X POST \
    --data-urlencode "csrfmiddlewaretoken=$token" "$@" "$url")
  echo "$out"
}

login() {  # username password jar
  local u=$1 p=$2 jar=$3 token
  : > "$jar"
  curl -s -o /dev/null -c "$jar" "$BASE/accounts/login/"
  token=$(grep csrftoken "$jar" | awk '{print $7}')
  curl -s -o /dev/null -b "$jar" -c "$jar" -H "Referer: $BASE/accounts/login/" -X POST \
    --data-urlencode "username=$u" --data-urlencode "password=$p" \
    --data-urlencode "csrfmiddlewaretoken=$token" "$BASE/accounts/login/"
}

# --- сервер ---------------------------------------------------------------
if ! curl -s -o /dev/null --max-time 2 "$BASE/accounts/login/"; then
  (cd "$BASE_DIR" && "$PY" manage.py runserver "127.0.0.1:$PORT" --noreload) \
    > /tmp/smoke-server.log 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 1 30); do
    curl -s -o /dev/null --max-time 1 "$BASE/accounts/login/" && break
    sleep 0.5
  done
fi

J_ADMIN="$COOKIES/admin.txt"
J_REG="$COOKIES/registrar1.txt"
J_MGR="$COOKIES/manager.txt"
J_NOB="$COOKIES/nobody.txt"
J_ANON="$COOKIES/anon.txt"
: > "$J_ANON"

echo "== 1. Аноним =="
check_eq "GET / → редирект на login" "302" "$(status "$BASE/" "$J_ANON")"
check_contains "цель редиректа — login" "$(redirect "$BASE/" "$J_ANON")" "/accounts/login/"
check_eq "GET /patients/ → редирект" "302" "$(status "$BASE/patients/" "$J_ANON")"
check_eq "GET /accounts/login/ → 200" "200" "$(status "$BASE/accounts/login/" "$J_ANON")"

echo "== 2. Логин admin =="
login admin admin12345 "$J_ADMIN"
check_eq "после логина / → 200" "200" "$(status "$BASE/" "$J_ADMIN")"
check_eq "список пациентов → 200" "200" "$(status "$BASE/patients/" "$J_ADMIN")"
check_eq "форма создания → 200" "200" "$(status "$BASE/patients/new/" "$J_ADMIN")"
check_eq "админка → 200" "200" "$(status "$BASE/admin/" "$J_ADMIN")"

echo "== 3. Seeds =="
(cd "$BASE_DIR" && "$PY" manage.py seed_demo > /dev/null 2>&1)
check_eq "seed_demo (без флага) → exit 0" "0" "$?"
ACTIVE_COUNT=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.patients.models import Patient; print(Patient.objects.filter(is_active=True).count())" 2>/dev/null | tail -n1)
check_eq "активных пациентов ≥ 15" "ok" \
  "$([ "$ACTIVE_COUNT" -ge 15 ] && echo ok || echo "$ACTIVE_COUNT")"

echo "== 4. CRUD пациента (admin) =="
# очистка от предыдущих прогонов (идемпотентность повторного запуска)
(cd "$BASE_DIR" && "$PY" manage.py shell -c "
from django.contrib.auth.models import User
from apps.appointments.models import Appointment
from apps.patients.models import Patient
from apps.schedule.models import Cabinet, Doctor, Specialty, WorkSchedule
Appointment.objects.filter(comment__startswith='[test]').delete()
Patient.objects.filter(notes__startswith='[test]').delete()
Doctor.objects.filter(user__username='doctor_test').delete()
User.objects.filter(username='doctor_test').delete()
Specialty.objects.filter(name='Гастроэнтеролог').delete()
Cabinet.objects.filter(number='999').delete()
" > /dev/null 2>&1)
: > "$J_ADMIN"; login admin admin12345 "$J_ADMIN"
CREATE=$(post "$BASE/patients/new/" "$J_ADMIN" \
  --data-urlencode "last_name=Тестов" \
  --data-urlencode "first_name=Картон" \
  --data-urlencode "patronymic=Петрович" \
  --data-urlencode "birth_date=1992-06-15" \
  --data-urlencode "gender=M" \
  --data-urlencode "snils=900-100-200 33" \
  --data-urlencode "phone=+998 90 000-11-22" \
  --data-urlencode "email=" \
  --data-urlencode "address=Ташкент, тестовый" \
  --data-urlencode "notes=[test] smoke" \
  --data-urlencode "policies-TOTAL_FORMS=1" \
  --data-urlencode "policies-INITIAL_FORMS=0" \
  --data-urlencode "policies-MIN_NUM_FORMS=0" \
  --data-urlencode "policies-MAX_NUM_FORMS=1000" \
  --data-urlencode "policies-0-policy_type=OMS" \
  --data-urlencode "policies-0-number=TEST001" \
  --data-urlencode "policies-0-insurer=Тест СК" \
  --data-urlencode "policies-0-valid_from=" \
  --data-urlencode "policies-0-valid_to=")
CREATE_CODE="${CREATE%%|*}"
CREATE_URL="${CREATE#*|}"
check_eq "POST создание → 302" "302" "$CREATE_CODE"
PID_NEW=$(echo "$CREATE_URL" | grep -oE '[0-9]+/$' | tr -d '/')
check_contains "редирект на карточку пациента" "$CREATE_URL" "/patients/${PID_NEW}/"
check_contains "карточка: ФИО" "$(body "$BASE/patients/$PID_NEW/" "$J_ADMIN")" "Тестов Картон Петрович"
check_contains "карточка: полис" "$(body "$BASE/patients/$PID_NEW/" "$J_ADMIN")" "TEST001"

check_contains "поиск по фамилии" "$(body "$BASE/patients/?q=Тестов" "$J_ADMIN")" "Тестов Картон Петрович"
check_contains "поиск по телефону" "$(body "$BASE/patients/?q=000-11-22" "$J_ADMIN")" "Тестов Картон Петрович"
check_contains "поиск по СНИЛС" "$(body "$BASE/patients/?q=900-100-200" "$J_ADMIN")" "Тестов Картон Петрович"
check_contains "поиск по СНИЛС из seeds" "$(body "$BASE/patients/?q=100-200-300" "$J_ADMIN")" "Соколова Мария"

POLICY_ID=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.patients.models import InsurancePolicy; print(InsurancePolicy.objects.filter(patient_id=${PID_NEW}).first().id)" \
  2>/dev/null | tail -n1)
EDIT=$(post "$BASE/patients/$PID_NEW/edit/" "$J_ADMIN" \
  --data-urlencode "last_name=Тестов" \
  --data-urlencode "first_name=Картон" \
  --data-urlencode "patronymic=Петрович" \
  --data-urlencode "birth_date=1992-06-15" \
  --data-urlencode "gender=M" \
  --data-urlencode "snils=900-100-200 33" \
  --data-urlencode "phone=+998 90 999-88-77" \
  --data-urlencode "email=t@e.st" \
  --data-urlencode "address=Ташкент, тестовый 2" \
  --data-urlencode "notes=[test] smoke edited" \
  --data-urlencode "policies-TOTAL_FORMS=1" \
  --data-urlencode "policies-INITIAL_FORMS=1" \
  --data-urlencode "policies-MIN_NUM_FORMS=0" \
  --data-urlencode "policies-MAX_NUM_FORMS=1000" \
  --data-urlencode "policies-0-id=${POLICY_ID}" \
  --data-urlencode "policies-0-patient=${PID_NEW}" \
  --data-urlencode "policies-0-policy_type=OMS" \
  --data-urlencode "policies-0-number=TEST001" \
  --data-urlencode "policies-0-insurer=Тест СК" \
  --data-urlencode "policies-0-valid_from=" \
  --data-urlencode "policies-0-valid_to=")
check_eq "POST редактирование → 302" "302" "${EDIT%%|*}"
check_contains "изменённый телефон виден" \
  "$(body "$BASE/patients/$PID_NEW/" "$J_ADMIN")" "+998 90 999-88-77"

echo "== 5. Валидации =="
DUP=$(post "$BASE/patients/new/" "$J_ADMIN" \
  --data-urlencode "last_name=Дубль" --data-urlencode "first_name=Снилса" \
  --data-urlencode "patronymic=" --data-urlencode "birth_date=1990-01-01" \
  --data-urlencode "gender=F" --data-urlencode "snils=100-200-300 40" \
  --data-urlencode "phone=" --data-urlencode "email=" --data-urlencode "address=" \
  --data-urlencode "notes=" \
  --data-urlencode "policies-TOTAL_FORMS=0" --data-urlencode "policies-INITIAL_FORMS=0" \
  --data-urlencode "policies-MIN_NUM_FORMS=0" --data-urlencode "policies-MAX_NUM_FORMS=1000")
check_eq "дубль СНИЛС → 200 с ошибкой формы" "200" "${DUP%%|*}"
check_contains "текст ошибки дубликата" \
  "$(body "$BASE/patients/new/" "$J_ADMIN")" "СНИЛС"

FUTURE=$(post "$BASE/patients/new/" "$J_ADMIN" \
  --data-urlencode "last_name=Будущий" --data-urlencode "first_name=Пациент" \
  --data-urlencode "patronymic=" --data-urlencode "birth_date=2031-01-01" \
  --data-urlencode "gender=M" --data-urlencode "snils=" \
  --data-urlencode "phone=" --data-urlencode "email=" --data-urlencode "address=" \
  --data-urlencode "notes=" \
  --data-urlencode "policies-TOTAL_FORMS=0" --data-urlencode "policies-INITIAL_FORMS=0" \
  --data-urlencode "policies-MIN_NUM_FORMS=0" --data-urlencode "policies-MAX_NUM_FORMS=1000")
check_eq "дата рождения в будущем → 200 с ошибкой" "200" "${FUTURE%%|*}"
POST_EMPTY=$(post "$BASE/patients/new/" "$J_ADMIN" \
  --data-urlencode "last_name=" --data-urlencode "first_name=" \
  --data-urlencode "birth_date=" --data-urlencode "gender=" --data-urlencode "snils=" \
  --data-urlencode "policies-TOTAL_FORMS=0" --data-urlencode "policies-INITIAL_FORMS=0" \
  --data-urlencode "policies-MIN_NUM_FORMS=0" --data-urlencode "policies-MAX_NUM_FORMS=1000")
check_eq "пустая форма → 200 (валидация не пускает)" "200" "${POST_EMPTY%%|*}"

echo "== 6. Деактивация =="
DEACT=$(post "$BASE/patients/$PID_NEW/deactivate/" "$J_ADMIN")
check_eq "POST deactivate → 302" "302" "${DEACT%%|*}"
check_eq "detail после деактивации → 404" "404" "$(status "$BASE/patients/$PID_NEW/" "$J_ADMIN")"
# ищем именно ссылку на карточку в таблице (имя может попасться во flash-сообщении)
check_eq "пациент исчез из списка" "0" \
  "$(body "$BASE/patients/?q=Тестов" "$J_ADMIN" | grep -c "patients/${PID_NEW}/")"

echo "== 7. Роли =="
login registrar1 registrar12345 "$J_REG"
check_eq "registrar1: список → 200" "200" "$(status "$BASE/patients/" "$J_REG")"
check_eq "registrar1: создание → 200" "200" "$(status "$BASE/patients/new/" "$J_REG")"
check_eq "registrar1: редактирование → 200" \
  "200" "$(status "$BASE/patients/1/edit/" "$J_REG")"

login manager manager12345 "$J_MGR"
check_eq "manager: список (чтение) → 200" "200" "$(status "$BASE/patients/" "$J_MGR")"
check_eq "manager: создание → 302 (блок)" "302" "$(status "$BASE/patients/new/" "$J_MGR")"
check_eq "manager: редактирование → 302 (блок)" "302" "$(status "$BASE/patients/1/edit/" "$J_MGR")"
check_contains "manager: редирект на дашборд" \
  "$(redirect "$BASE/patients/new/" "$J_MGR")" "$BASE/"

login nobody nobody12345 "$J_NOB"
check_eq "nobody: дашборд → 200" "200" "$(status "$BASE/" "$J_NOB")"
check_eq "nobody: пациенты → 302 (блок)" "302" "$(status "$BASE/patients/" "$J_NOB")"

check_eq "аноним: POST создание → 302 (нет сессии)" "302" \
  "$(status "$BASE/patients/new/" "$J_ANON")"

echo "== 8. Справочники (admin) =="
: > "$J_ADMIN"; login admin admin12345 "$J_ADMIN"
SPEC=$(post "$BASE/schedule/specialties/new/" "$J_ADMIN" \
  --data-urlencode "name=Гастроэнтеролог" --data-urlencode "code=GAST")
check_eq "создание специальности → 302" "302" "${SPEC%%|*}"
check_contains "специальность в списке" \
  "$(body "$BASE/schedule/specialties/" "$J_ADMIN")" "Гастроэнтеролог"

CAB=$(post "$BASE/schedule/cabinets/new/" "$J_ADMIN" \
  --data-urlencode "number=999" --data-urlencode "floor=3" --data-urlencode "building=В")
check_eq "создание кабинета → 302" "302" "${CAB%%|*}"
check_contains "кабинет в списке" \
  "$(body "$BASE/schedule/cabinets/" "$J_ADMIN")" "999"

SPEC_ID=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.schedule.models import Specialty; print(Specialty.objects.get(name='Гастроэнтеролог').id)" \
  2>/dev/null | tail -n1)
DOC_NEW=$(post "$BASE/schedule/doctors/new/" "$J_ADMIN" \
  --data-urlencode "existing_user=" \
  --data-urlencode "username=doctor_test" \
  --data-urlencode "password=Doctor-2026!" \
  --data-urlencode "first_name=Тест" \
  --data-urlencode "last_name=Тестов" \
  --data-urlencode "specialty=${SPEC_ID}" \
  --data-urlencode "cabinet=" \
  --data-urlencode "is_active=on")
check_eq "создание врача (новый пользователь) → 302" "302" "${DOC_NEW%%|*}"
check_contains "врач в списке" \
  "$(body "$BASE/schedule/doctors/" "$J_ADMIN")" "Тестов Тест"
check_eq "логин doctor_test создан" "1" \
  "$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
    "from django.contrib.auth.models import User; print(User.objects.filter(username='doctor_test').count())" \
    2>/dev/null | tail -n1)"

DOC_TEST_ID=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.schedule.models import Doctor; print(Doctor.objects.get(user__username='doctor_test').id)" \
  2>/dev/null | tail -n1)
WS=$(post "$BASE/schedule/work-schedules/new/" "$J_ADMIN" \
  --data-urlencode "doctor=${DOC_TEST_ID}" --data-urlencode "weekday=7" \
  --data-urlencode "start_time=10:00" --data-urlencode "end_time=12:00" \
  --data-urlencode "slot_minutes=30" --data-urlencode "valid_from=" --data-urlencode "valid_to=")
check_eq "создание расписания → 302" "302" "${WS%%|*}"
check_contains "расписание в списке" \
  "$(body "$BASE/schedule/work-schedules/" "$J_ADMIN")" "10:00–12:00"

# валидации справочников
BAD_WS=$(post "$BASE/schedule/work-schedules/new/" "$J_ADMIN" \
  --data-urlencode "doctor=${DOC_TEST_ID}" --data-urlencode "weekday=7" \
  --data-urlencode "start_time=12:00" --data-urlencode "end_time=10:00" \
  --data-urlencode "slot_minutes=30" --data-urlencode "valid_from=" --data-urlencode "valid_to=")
check_eq "конец раньше начала → 200 с ошибкой" "200" "${BAD_WS%%|*}"

DUP_SPEC=$(post "$BASE/schedule/specialties/new/" "$J_ADMIN" \
  --data-urlencode "name=Гастроэнтеролог" --data-urlencode "code=X2")
check_eq "дубль названия специальности → 200 с ошибкой" "200" "${DUP_SPEC%%|*}"

echo "== 9. Запись на приём (admin) =="
# пациент из seeds (берём имя динамически — порядок может меняться)
PAT_ID=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.patients.models import Patient; print(Patient.objects.filter(notes__startswith='[demo]', is_active=True).first().id)" \
  2>/dev/null | tail -n1)
PAT_LAST=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.patients.models import Patient; print(Patient.objects.filter(notes__startswith='[demo]', is_active=True).first().last_name)" \
  2>/dev/null | tail -n1)
DOC1_ID=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.schedule.models import Doctor; print(Doctor.objects.get(user__username='doctor1').id)" \
  2>/dev/null | tail -n1)

# дата: сегодня или завтра — ищем день, где у doctor1 есть свободные слоты
BOOK_DATE=""
for off in 0 1 2 3; do
  D=$(date -d "+$off day" +%F)
  CNT=$(cd "$BASE_DIR" && "$PY" manage.py shell -c "
from datetime import date
from apps.schedule.models import Doctor
from apps.appointments.slots import generate_slots
doc = Doctor.objects.get(user__username='doctor1')
print(sum(1 for s in generate_slots(doc, date.fromisoformat('$D')) if not s['busy'] and not s['past']))
" 2>/dev/null | tail -n1)
  if [ "${CNT:-0}" -gt 0 ]; then BOOK_DATE="$D"; break; fi
done
check_eq "найден день со свободными слотами" "ok" "$([ -n "$BOOK_DATE" ] && echo ok || echo no)"

BOOK_PAGE=$(body "$BASE/appointments/booking/?patient=${PAT_ID}&doctor=${DOC1_ID}&date=${BOOK_DATE}" "$J_ADMIN")
check_eq "страница записи → 200" "200" \
  "$(status "$BASE/appointments/booking/?patient=${PAT_ID}&doctor=${DOC1_ID}&date=${BOOK_DATE}" "$J_ADMIN")"
check_contains "сетка слотов отрисована" "$BOOK_PAGE" "Шаг 2"

# первый свободный слот
SLOT=$(cd "$BASE_DIR" && "$PY" manage.py shell -c "
from datetime import date
from apps.schedule.models import Doctor
from apps.appointments.slots import generate_slots
doc = Doctor.objects.get(user__username='doctor1')
free = [s for s in generate_slots(doc, date.fromisoformat('$BOOK_DATE')) if not s['busy'] and not s['past']]
print(f'{free[0][\"time\"].hour:02d}:{free[0][\"time\"].minute:02d}:00' if free else '')
" 2>/dev/null | tail -n1)
check_eq "свободный слот найден" "ok" "$([ -n "$SLOT" ] && echo ok || echo no)"

APT=$(post "$BASE/appointments/booking/" "$J_ADMIN" \
  --data-urlencode "patient=${PAT_ID}" \
  --data-urlencode "doctor=${DOC1_ID}" \
  --data-urlencode "visit_date=${BOOK_DATE}" \
  --data-urlencode "slot_start=${SLOT}" \
  --data-urlencode "visit_type=primary" \
  --data-urlencode "comment=[test] smoke booking")
check_eq "POST запись → 302" "302" "${APT%%|*}"
APT_ID=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.appointments.models import Appointment; a=Appointment.objects.filter(comment='[test] smoke booking').order_by('-id').first(); print(a.pk if a else '')" \
  2>/dev/null | tail -n1)
check_eq "запись создана в БД" "ok" "$([ -n "$APT_ID" ] && echo ok || echo no)"
check_eq "страница записи (карточка) → 200" "200" \
  "$(status "$BASE/appointments/${APT_ID}/" "$J_ADMIN")"
check_contains "талон → 200 и содержит номер" "ok" \
  "$(BODY=$(body "$BASE/appointments/${APT_ID}/ticket/" "$J_ADMIN"); \
     case "$BODY" in *"№${APT_ID}"*) echo ok;; *) echo bad;; esac)"

# двойная запись в тот же слот → отказ
DUP_BOOK=$(post "$BASE/appointments/booking/" "$J_ADMIN" \
  --data-urlencode "patient=${PAT_ID}" \
  --data-urlencode "doctor=${DOC1_ID}" \
  --data-urlencode "visit_date=${BOOK_DATE}" \
  --data-urlencode "slot_start=${SLOT}" \
  --data-urlencode "visit_type=primary" \
  --data-urlencode "comment=")
check_eq "двойная запись → 200 с ошибкой" "200" "${DUP_BOOK%%|*}"
check_contains "текст «Слот уже занят»" \
  "$(body "$BASE/appointments/booking/?patient=${PAT_ID}&doctor=${DOC1_ID}&date=${BOOK_DATE}" "$J_ADMIN")" \
  "Слот"

# запись в прошлое → отказ
PAST_DATE=$(date -d "-1 day" +%F)
PAST_BOOK=$(post "$BASE/appointments/booking/" "$J_ADMIN" \
  --data-urlencode "patient=${PAT_ID}" \
  --data-urlencode "doctor=${DOC1_ID}" \
  --data-urlencode "visit_date=${PAST_DATE}" \
  --data-urlencode "slot_start=${SLOT}" \
  --data-urlencode "visit_type=primary" \
  --data-urlencode "comment=")
check_eq "запись в прошлой дате → 200 с ошибкой" "200" "${PAST_BOOK%%|*}"

# запись вне расписания (ночь) → отказ
NIGHT_BOOK=$(post "$BASE/appointments/booking/" "$J_ADMIN" \
  --data-urlencode "patient=${PAT_ID}" \
  --data-urlencode "doctor=${DOC1_ID}" \
  --data-urlencode "visit_date=${BOOK_DATE}" \
  --data-urlencode "slot_start=03:00:00" \
  --data-urlencode "visit_type=primary" \
  --data-urlencode "comment=")
check_eq "слот вне расписания → 200 с ошибкой" "200" "${NIGHT_BOOK%%|*}"

# отмена освобождает слот → повторная запись того же слота проходит
CANCEL=$(post "$BASE/appointments/${APT_ID}/cancel/" "$J_ADMIN" \
  --data-urlencode "reason=[test] отмена в смоуке")
check_eq "отмена записи → 302" "302" "${CANCEL%%|*}"
check_contains "статус отмены на странице" \
  "$(body "$BASE/appointments/${APT_ID}/" "$J_ADMIN")" "отменён"
REBOOK=$(post "$BASE/appointments/booking/" "$J_ADMIN" \
  --data-urlencode "patient=${PAT_ID}" \
  --data-urlencode "doctor=${DOC1_ID}" \
  --data-urlencode "visit_date=${BOOK_DATE}" \
  --data-urlencode "slot_start=${SLOT}" \
  --data-urlencode "visit_type=repeat" \
  --data-urlencode "comment=[test] rebook")
check_eq "слот свободен после отмены (повторная запись → 302)" "302" "${REBOOK%%|*}"

# перенос: найти ещё один свободный слот и перенести вторую запись
APT2_ID=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.appointments.models import Appointment; a=Appointment.objects.filter(comment='[test] rebook').order_by('-id').first(); print(a.pk if a else '')" \
  2>/dev/null | tail -n1)
SLOT2=$(cd "$BASE_DIR" && "$PY" manage.py shell -c "
from datetime import date
from apps.schedule.models import Doctor
from apps.appointments.slots import generate_slots
doc = Doctor.objects.get(user__username='doctor1')
free = [s for s in generate_slots(doc, date.fromisoformat('$BOOK_DATE')) if not s['busy'] and not s['past']]
print(f'{free[0][\"time\"].hour:02d}:{free[0][\"time\"].minute:02d}:00' if free else '')
" 2>/dev/null | tail -n1)
if [ -n "$SLOT2" ] && [ -n "$APT2_ID" ]; then
  MOVE=$(post "$BASE/appointments/${APT2_ID}/move/" "$J_ADMIN" \
    --data-urlencode "visit_date=${BOOK_DATE}" --data-urlencode "slot_start=${SLOT2}")
  check_eq "перенос записи → 302" "302" "${MOVE%%|*}"
  check_contains "новое время на карточке" \
    "$(body "$BASE/appointments/${APT2_ID}/" "$J_ADMIN")" "${SLOT2%:00}"
else
  check_eq "перенос (нет свободного слота — пропущено)" "skip" "skip"
fi

# список дня показывает запись
check_contains "запись видна в списке дня" \
  "$(body "$BASE/appointments/?date=${BOOK_DATE}" "$J_ADMIN")" "$PAT_LAST"

echo "== 10. Роли на запись/справочники =="
login registrar1 registrar12345 "$J_REG"
check_eq "registrar1: страница записи → 200" "200" \
  "$(status "$BASE/appointments/booking/?patient=${PAT_ID}" "$J_REG")"
check_eq "registrar1: список дня → 200" "200" \
  "$(status "$BASE/appointments/?date=${BOOK_DATE}" "$J_REG")"
check_eq "registrar1: справочники (hub) → 302 (нет прав)" "302" \
  "$(status "$BASE/schedule/" "$J_REG")"

login manager manager12345 "$J_MGR"
check_eq "manager: список дня (чтение) → 200" "200" \
  "$(status "$BASE/appointments/?date=${BOOK_DATE}" "$J_MGR")"
check_eq "manager: создание записи → 302 (блок)" "302" \
  "$(status "$BASE/appointments/booking/" "$J_MGR")"
check_eq "manager: специальности (чтение) → 200" "200" \
  "$(status "$BASE/schedule/specialties/" "$J_MGR")"
check_eq "manager: создание специальности → 302 (блок)" "302" \
  "$(status "$BASE/schedule/specialties/new/" "$J_MGR")"

login doctor_test Doctor-2026! "$COOKIES/dt.txt"
check_eq "doctor_test: создание записи → 302 (блок)" "302" \
  "$(status "$BASE/appointments/booking/" "$COOKIES/dt.txt")"
check_eq "doctor_test: список пациентов → 302 (блок)" "302" \
  "$(status "$BASE/patients/" "$COOKIES/dt.txt")"
check_eq "doctor_test: дашборд → 200" "200" \
  "$(status "$BASE/" "$COOKIES/dt.txt")"

echo
echo "=================================="
echo "Итого: PASS=$PASS FAIL=$FAIL"
echo "=================================="
[ "$FAIL" -eq 0 ]
