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
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null
    # ждём graceful-выход, иначе следующий прогон может подхватить
    # умирающий сервер по уже открытому порту
    for _ in $(seq 1 20); do
      kill -0 "$SERVER_PID" 2>/dev/null || break
      sleep 0.1
    done
    kill -9 "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
  fi
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

post_body() {  # url jar [key=val...] -> html-тело ответа POST (для проверки ошибок)
  local url=$1 jar=$2; shift 2
  local token
  token=$(grep csrftoken "$jar" | awk '{print $7}' | tail -n1)
  curl -s -b "$jar" -c "$jar" -H "Referer: $url" -X POST \
    --data-urlencode "csrfmiddlewaretoken=$token" "$@" "$url"
}

post_file() {  # url jar file path [key=val...] -> "code|redirect_url" (multipart, для фото)
  local url=$1 jar=$2 file=$3; shift 3
  local token out args=() kv
  token=$(grep csrftoken "$jar" | awk '{print $7}' | tail -n1)
  args+=(-F "csrfmiddlewaretoken=$token")
  for kv in "$@"; do args+=(-F "$kv"); done
  out=$(curl -s -o /dev/null -w '%{http_code}|%{redirect_url}' \
    -b "$jar" -c "$jar" -H "Referer: $url" "${args[@]}" \
    -F "photo=@${file};type=image/png" "$url")
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
check_eq "GET / → публичная главная (200)" "200" "$(status "$BASE/" "$J_ANON")"
check_contains "главная: ссылка на вход для сотрудников" \
  "$(body "$BASE/" "$J_ANON")" "/accounts/login/"
check_contains "главная: каталог врачей" \
  "$(body "$BASE/" "$J_ANON")" "/doctors/"
check_contains "главная: монитор очереди" \
  "$(body "$BASE/" "$J_ANON")" "/queue/monitor/"
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
from apps.schedule.models import Cabinet, Department, Doctor, Specialty, WorkSchedule
Appointment.objects.filter(comment__startswith='[test]').delete()
Direction.objects.filter(reason__startswith='[test]').delete()
Patient.objects.filter(notes__startswith='[test]').delete()
# удаляем вместе с загруженным в смоуке фото (файловые сироты недопустимы)
for _d in Doctor.objects.filter(user__username__in=('doctor_test', 'doctor_test2')):
    _d.photo.delete(save=False)
Doctor.objects.filter(user__username__in=('doctor_test', 'doctor_test2')).delete()
User.objects.filter(username__in=('doctor_test', 'doctor_test2')).delete()
Specialty.objects.filter(name__endswith='[test]', doctors__isnull=True).delete()
Cabinet.objects.filter(number='999').delete()
Department.objects.filter(name='Тестовый отдел [test]').delete()
# демо-талоны: вернуть «живых» в очередь (смоук мог вызвать пациентов)
from apps.queue.models import QueueTicket
QueueTicket.objects.filter(appointment__comment__startswith='[demo]') \
    .exclude(status__in=('completed', 'no_show', 'cancelled')) \
    .update(status='waiting', called_at=None, started_at=None, finished_at=None)
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

echo "== 6б. Публичная страница пациента (без входа) =="
PUB_UUID=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.patients.models import Patient; print(Patient.objects.filter(last_name='Соколова').first().public_id)" \
  2>/dev/null | tail -n1)
check_eq "формат public_id — UUID" "1" \
  "$(echo "$PUB_UUID" | grep -cE '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')"
check_eq "аноним: /p/<uuid>/ → 200" "200" \
  "$(status "$BASE/p/${PUB_UUID}/" "$J_ANON")"
check_contains "страница: ФИО пациента" \
  "$(body "$BASE/p/${PUB_UUID}/" "$J_ANON")" "Соколова"
check_eq "неизвестный UUID → 404" "404" \
  "$(status "$BASE/p/00000000-0000-4000-8000-000000000000/" "$J_ANON")"
check_eq "некорректный UUID → 404" "404" \
  "$(status "$BASE/p/not-a-uuid/" "$J_ANON")"
DEACT_UUID=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.patients.models import Patient; p=Patient.objects.filter(last_name='Тестов').order_by('-pk').first(); print(p.public_id if p else '')" \
  2>/dev/null | tail -n1)
check_eq "деактивированный пациент → 404" "404" \
  "$(status "$BASE/p/${DEACT_UUID}/" "$J_ANON")"
check_contains "карточка: ссылка для пациента видна персоналу" \
  "$(body "$BASE/patients/1/" "$J_ADMIN")" "/p/"

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
# CRUD специальности проверяем на тестовой записи: Гастроэнтеролог
# теперь в seeds (за ним закреплены демо-врачи), удалять его нельзя
SPEC=$(post "$BASE/schedule/specialties/new/" "$J_ADMIN" \
  --data-urlencode "name=Ревматолог [test]" --data-urlencode "code=RHE")
check_eq "создание специальности → 302" "302" "${SPEC%%|*}"
check_contains "специальность в списке" \
  "$(body "$BASE/schedule/specialties/" "$J_ADMIN")" "Ревматолог"

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
  --data-urlencode "name=Ревматолог [test]" --data-urlencode "code=X2")
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

# дата: ищем день, где у doctor1 есть свободные слоты с запасом:
# нужно ≥3 (один займёт первая запись, ещё один — перенос, третий — страховка
# от «past» у ближайших слотов). К концу дня «сегодня» перестаёт подходить,
# и смоук стабильно уходит на завтра — количество проверок не плавает.
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
  if [ "${CNT:-0}" -ge 3 ]; then BOOK_DATE="$D"; break; fi
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
check_contains "талон: персональная ссылка пациента" \
  "$(body "$BASE/appointments/${APT_ID}/ticket/" "$J_ADMIN")" "/p/"
# пациент видит свою запись по ссылке (аноним, без входа);
# дата на странице отображается как дд.мм.гггг — приводим BOOK_DATE к тому же виду
PAT_UUID=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.patients.models import Patient; print(Patient.objects.get(pk=${PAT_ID}).public_id)" \
  2>/dev/null | tail -n1)
BOOK_DATE_HR="${BOOK_DATE:8:2}.${BOOK_DATE:5:2}.${BOOK_DATE:0:4}"
check_contains "аноним: страница пациента содержит созданную запись" \
  "$(body "$BASE/p/${PAT_UUID}/" "$J_ANON")" "${BOOK_DATE_HR}"

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

echo "== 11. Электронная очередь и кабинет врача =="
TODAY=$(date +%F)

# талон создаётся автоматически при записи
check_eq "талон создан для записи из смоука" "1" \
  "$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
    "from apps.queue.models import QueueTicket; print(QueueTicket.objects.filter(appointment_id=${APT2_ID}, status='waiting').count())" \
    2>/dev/null | tail -n1)"

# аноним: монитор открыт без входа, очередь — за логином
check_eq "аноним: монитор → 200" "200" "$(status "$BASE/queue/monitor/" "$J_ANON")"
check_eq "аноним: очередь → 302 (login)" "302" "$(status "$BASE/queue/" "$J_ANON")"
check_eq "монитор без имён пациентов" "0" \
  "$(body "$BASE/queue/monitor/" "$J_ANON" | grep -c "$PAT_LAST")"

# admin: список очереди
check_eq "admin: очередь → 200" "200" "$(status "$BASE/queue/" "$J_ADMIN")"
check_contains "admin: кнопка вызова есть" \
  "$(body "$BASE/queue/" "$J_ADMIN")" "Вызвать следующего"

# doctor1: кабинет видит свою запись, чужую — нет
J_DOC1="$COOKIES/doctor1.txt"
login doctor1 doctor12345 "$J_DOC1"
check_eq "doctor1: кабинет → 200" "200" \
  "$(status "$BASE/queue/cabinet/?date=${BOOK_DATE}" "$J_DOC1")"
CAB_BODY=$(body "$BASE/queue/cabinet/?date=${BOOK_DATE}" "$J_DOC1")
check_contains "кабинет: своя запись видна" "$CAB_BODY" "$PAT_LAST"
check_eq "кабинет: запись другого врача не видна" "0" \
  "$(echo "$CAB_BODY" | grep -c "Каримова")"
check_eq "doctor1: общая очередь (только чтение)" "0" \
  "$(body "$BASE/queue/" "$J_DOC1" | grep -c "Вызвать следующего")"

# doctor1: полный цикл call → start → complete с заметкой
TID=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.queue.models import QueueTicket; t=QueueTicket.objects.filter(appointment_id=${APT2_ID}).first(); print(t.pk if t else '')" \
  2>/dev/null | tail -n1)
check_eq "талон записи найден" "ok" "$([ -n "$TID" ] && echo ok || echo no)"

CALL=$(post "$BASE/queue/${TID}/action/" "$J_ADMIN" --data-urlencode "action=call")
check_eq "admin: вызов талона → 302" "302" "${CALL%%|*}"
check_eq "статус талона → called" "called" \
  "$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
    "from apps.queue.models import QueueTicket; print(QueueTicket.objects.get(pk=${TID}).status)" \
    2>/dev/null | tail -n1)"

MON_BODY=$(body "$BASE/queue/monitor/?date=${BOOK_DATE}" "$J_ANON")
MON_NUM=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.queue.models import QueueTicket; print(QueueTicket.objects.get(pk=${TID}).number)" \
  2>/dev/null | tail -n1)
check_contains "монитор показывает вызванный номер" "$MON_BODY" "№${MON_NUM}"

START=$(post "$BASE/queue/cabinet/${TID}/action/" "$J_DOC1" --data-urlencode "action=start")
check_eq "doctor1: приём начат → 302" "302" "${START%%|*}"
check_eq "статус талона → with_doctor" "with_doctor" \
  "$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
    "from apps.queue.models import QueueTicket; print(QueueTicket.objects.get(pk=${TID}).status)" \
    2>/dev/null | tail -n1)"

DONE=$(post "$BASE/queue/cabinet/${TID}/action/" "$J_DOC1" \
  --data-urlencode "action=complete" \
  --data-urlencode "visit_note=[test] осмотр завершён")
check_eq "doctor1: завершение приёма → 302" "302" "${DONE%%|*}"
check_eq "талон → completed" "completed" \
  "$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
    "from apps.queue.models import QueueTicket; print(QueueTicket.objects.get(pk=${TID}).status)" \
    2>/dev/null | tail -n1)"
check_contains "запись завершена, заметка врача сохранена" \
  "$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
    "from apps.appointments.models import Appointment; a=Appointment.objects.get(pk=${APT2_ID}); print(a.status, a.visit_note)" \
    2>/dev/null | tail -n1)" "[test] осмотр завершён"

# изоляция: doctor1 не может завершать талоны другого врача
TID2=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.queue.models import QueueTicket; t=QueueTicket.objects.filter(status='waiting').exclude(doctor__user__username='doctor1').first(); print(t.pk if t else '')" \
    2>/dev/null | tail -n1)
if [ -n "$TID2" ]; then
  FOREIGN=$(post "$BASE/queue/cabinet/${TID2}/action/" "$J_DOC1" --data-urlencode "action=start")
  check_contains "чужой талон: редирект с ошибкой (без параметров)" \
    "${FOREIGN#*|}" "$BASE/queue/cabinet/"
  check_eq "чужой талон не изменился" "waiting" \
    "$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
      "from apps.queue.models import QueueTicket; print(QueueTicket.objects.get(pk=${TID2}).status)" \
      2>/dev/null | tail -n1)"
else
  check_eq "изоляция (нет чужого талона — пропущено)" "skip" "skip"
  check_eq "изоляция (нет чужого талона — пропущено)" "skip" "skip"
fi

# manager: очередь только читает
login manager manager12345 "$J_MGR"
check_eq "manager: очередь (чтение) → 200" "200" "$(status "$BASE/queue/" "$J_MGR")"
MCALL=$(post "$BASE/queue/call-next/" "$J_MGR" \
  --data-urlencode "doctor=${DOC1_ID}" --data-urlencode "date=${BOOK_DATE}")
check_eq "manager: вызов → 302 (блок роли)" "302" "${MCALL%%|*}"
check_contains "manager: редирект на дашборд" "${MCALL#*|}" "$BASE/"

# doctor_test: кабинет пуст (нет своих записей), но доступен
login doctor_test Doctor-2026! "$COOKIES/dt.txt"
check_eq "doctor_test: кабинет → 200" "200" \
  "$(status "$BASE/queue/cabinet/" "$COOKIES/dt.txt")"
check_eq "doctor_test: чужие записи не видны" "0" \
  "$(body "$BASE/queue/cabinet/" "$COOKIES/dt.txt" | grep -c "$PAT_LAST")"
check_eq "doctor_test: вызов в общей очереди → 302 (блок)" "302" \
  "$(post "$BASE/queue/call-next/" "$COOKIES/dt.txt" \
    --data-urlencode "doctor=${DOC1_ID}" --data-urlencode "date=${BOOK_DATE}" | cut -d'|' -f1)"

echo "== 12. Отчёты =="
# аноним и роли без доступа
check_eq "аноним: /reports/ → 302 (login)" "302" "$(status "$BASE/reports/" "$J_ANON")"
login registrar1 registrar12345 "$J_REG"
check_eq "registrar: /reports/ → 302 (нет прав)" "302" "$(status "$BASE/reports/" "$J_REG")"

# admin: все три отчёта
: > "$J_ADMIN"; login admin admin12345 "$J_ADMIN"
check_eq "admin: хаб отчётов → 200" "200" "$(status "$BASE/reports/" "$J_ADMIN")"
check_eq "admin: загрузка врачей → 200" "200" "$(status "$BASE/reports/load/" "$J_ADMIN")"
check_eq "admin: неявки → 200" "200" "$(status "$BASE/reports/no-shows/" "$J_ADMIN")"
check_eq "admin: поток пациентов → 200" "200" "$(status "$BASE/reports/flow/" "$J_ADMIN")"

# данные из seeds видны в отчётах (период — 30 дней назад, чтобы покрыть историю)
P_FROM=$(date -d "-30 day" +%F)
P_TO=$(date -d "+1 day" +%F)
LOAD_BODY=$(body "$BASE/reports/load/?from=${P_FROM}&to=${P_TO}" "$J_ADMIN")
check_contains "загрузка: есть демо-врач" "$LOAD_BODY" "Орлов"
check_contains "загрузка: % загрузки отображается" "$LOAD_BODY" "% загрузки"
NS_BODY=$(body "$BASE/reports/no-shows/?from=${P_FROM}&to=${P_TO}" "$J_ADMIN")
NS_PAT=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.appointments.models import Appointment; a=Appointment.objects.filter(status='no_show', comment__startswith='[demo]').first(); print(a.patient.last_name if a else '')" \
  2>/dev/null | tail -n1)
check_contains "неявки: пациент из seeds в списке" "$NS_BODY" "$NS_PAT"
FLOW_BODY=$(body "$BASE/reports/flow/?from=${P_FROM}&to=${P_TO}" "$J_ADMIN")
check_contains "поток: пиковый день показан" "$FLOW_BODY" "Пик дня"

# валидация периода: from > to — автоматическая замена, без ошибки
check_eq "период from>to → 200 (auto-swap)" "200" \
  "$(status "$BASE/reports/load/?from=${P_TO}&to=${P_FROM}" "$J_ADMIN")"

# doctor: только свои цифры (изоляция)
J_DOC1="$COOKIES/doctor1.txt"
login doctor1 doctor12345 "$J_DOC1"
check_eq "doctor: хаб отчётов → 200" "200" "$(status "$BASE/reports/" "$J_DOC1")"
DOC_LOAD=$(body "$BASE/reports/load/?from=${P_FROM}&to=${P_TO}" "$J_DOC1")
check_contains "doctor: свой врач в отчёте" "$DOC_LOAD" "Орлов"
check_eq "doctor: чужой врач не виден" "0" "$(echo "$DOC_LOAD" | grep -c "Каримов")"
check_eq "doctor: селектор врачей скрыт" "0" \
  "$(body "$BASE/reports/" "$J_DOC1" | grep -c 'name="doctor"')"

# manager: чтение всех отчётов
login manager manager12345 "$J_MGR"
check_eq "manager: хаб отчётов → 200" "200" "$(status "$BASE/reports/" "$J_MGR")"
check_eq "manager: неявки → 200" "200" "$(status "$BASE/reports/no-shows/" "$J_MGR")"

# навигация
check_contains "ссылка «Отчёты» в меню (admin)" \
  "$(body "$BASE/" "$J_ADMIN")" "/reports/"
check_eq "registrar: ссылки «Отчёты» нет в меню" "0" \
  "$(body "$BASE/" "$J_REG" | grep -c '/reports/')"

echo "== 13. Этажи и кабинеты врачей =="
check_eq "аноним: /schedule/floors/ → 302 (login)" "302" \
  "$(status "$BASE/schedule/floors/" "$J_ANON")"
check_eq "registrar: кабинеты по этажам → 200" "200" \
  "$(status "$BASE/schedule/floors/" "$J_REG")"
GUIDE=$(body "$BASE/schedule/floors/" "$J_ADMIN")
check_contains "этажи: заголовок этажа" "$GUIDE" "1 этаж"
check_contains "этажи: кабинет 101 показан" "$GUIDE" "Кабинет 101"
check_contains "этажи: врач Орлов закреплён" "$GUIDE" "Орлов"
check_contains "этажи: ссылка на дашборде (admin)" \
  "$(body "$BASE/" "$J_ADMIN")" "/schedule/floors/"
check_contains "этажи: ссылка на дашборде (registrar)" \
  "$(body "$BASE/" "$J_REG")" "/schedule/floors/"
# фильтр по этажу в CRUD кабинетов
CAB2=$(body "$BASE/schedule/cabinets/?floor=2" "$J_ADMIN")
check_contains "фильтр ?floor=2: кабинет 201 виден" "$CAB2" "201"
check_eq "фильтр ?floor=2: кабинет 101 скрыт" "0" \
  "$(echo "$CAB2" | grep -c '<td>101</td>')"
check_contains "фильтр ?floor=2: пустые кабинеты без врачей" "$CAB2" "—"
check_eq "фильтр ?floor=999: пустое состояние, 200" "200" \
  "$(status "$BASE/schedule/cabinets/?floor=999" "$J_ADMIN")"
check_eq "registrar: CRUD кабинетов → 302 (нет прав)" "302" \
  "$(status "$BASE/schedule/cabinets/" "$J_REG")"

echo "== 14. Отделы =="
check_eq "аноним: /schedule/departments/ → 302 (login)" "302" \
  "$(status "$BASE/schedule/departments/" "$J_ANON")"
check_eq "registrar: отделы → 302 (нет прав)" "302" \
  "$(status "$BASE/schedule/departments/" "$J_REG")"
check_eq "admin: список отделов → 200" "200" \
  "$(status "$BASE/schedule/departments/" "$J_ADMIN")"
check_eq "manager: список отделов → 200 (чтение)" "200" \
  "$(status "$BASE/schedule/departments/" "$J_MGR")"
DEPTS=$(body "$BASE/schedule/departments/" "$J_ADMIN")
check_contains "отделы: демо-отдел в списке" "$DEPTS" "Терапевтическое отделение"
check_contains "отделы: колонка «Врачей»" "$DEPTS" "Врачей"
check_contains "ссылка «Отделы» в хабе справочников" \
  "$(body "$BASE/schedule/" "$J_ADMIN")" "/schedule/departments/"

# CRUD: создание / редактирование / дубль
DEPT=$(post "$BASE/schedule/departments/new/" "$J_ADMIN" \
  --data-urlencode "name=Тестовый отдел [test]" --data-urlencode "code=TST")
check_eq "создание отдела → 302" "302" "${DEPT%%|*}"
check_contains "новый отдел в списке" \
  "$(body "$BASE/schedule/departments/" "$J_ADMIN")" "Тестовый отдел"
DEPT_PK=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.schedule.models import Department; d=Department.objects.filter(name='Тестовый отдел [test]').first(); print(d.pk if d else '')" \
  2>/dev/null | tail -n1)
EDIT=$(post "$BASE/schedule/departments/$DEPT_PK/edit/" "$J_ADMIN" \
  --data-urlencode "name=Тестовый отдел [test]" --data-urlencode "code=TST2")
check_eq "редактирование отдела → 302" "302" "${EDIT%%|*}"
check_contains "код отдела обновлён" \
  "$(body "$BASE/schedule/departments/" "$J_ADMIN")" "TST2"
DUP=$(post "$BASE/schedule/departments/new/" "$J_ADMIN" \
  --data-urlencode "name=Тестовый отдел [test]" --data-urlencode "code=X")
check_eq "дубль названия отдела → 200 с ошибкой" "200" "${DUP%%|*}"
check_eq "manager: создание отдела → 302 (нет прав)" "302" \
  "$(status "$BASE/schedule/departments/new/" "$J_MGR")"

# фильтры: отдел как разрез
THERA_PK=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.schedule.models import Department; print(Department.objects.get(name='Терапевтическое отделение').pk)" \
  2>/dev/null | tail -n1)
DOCS_DEPT=$(body "$BASE/schedule/doctors/?department=$THERA_PK" "$J_ADMIN")
check_contains "врачи ?department=: Орлов виден" "$DOCS_DEPT" "Орлов"
check_eq "врачи ?department=: Каримов скрыт" "0" "$(echo "$DOCS_DEPT" | grep -c 'Каримов')"
check_contains "список врачей: колонка «Отдел»" \
  "$(body "$BASE/schedule/doctors/" "$J_ADMIN")" "Отдел"

GUIDE2=$(body "$BASE/schedule/floors/" "$J_ADMIN")
check_contains "этажи: отдел подписан у врача" "$GUIDE2" "Терапевтическое отделение"
check_contains "этажи: фильтр по отделам" "$GUIDE2" "?department="
GUIDE_DEPT=$(body "$BASE/schedule/floors/?department=$THERA_PK" "$J_ADMIN")
check_eq "этажи ?department=: Каримов скрыт" "0" "$(echo "$GUIDE_DEPT" | grep -c 'Каримов')"

RLOAD=$(body "$BASE/reports/load/?from=${P_FROM}&to=${P_TO}&department=$THERA_PK" "$J_ADMIN")
check_contains "отчёт ?department=: строка врача отдела" "$RLOAD" "text-muted small\">(Терапевт)"
check_eq "отчёт ?department=: чужой отдел без строки" "0" \
  "$(echo "$RLOAD" | grep -c 'text-muted small\">(Кардиолог)')"
check_contains "отчёт загрузки: колонка «Отдел»" \
  "$(body "$BASE/reports/load/?from=${P_FROM}&to=${P_TO}" "$J_ADMIN")" "<th>Отдел</th>"
check_eq "doctor: селектор отдела скрыт" "0" \
  "$(body "$BASE/reports/" "$J_DOC1" | grep -c 'name="department"')"

echo "== 15. Отделы и специальности =="
check_eq "аноним: /schedule/structure/ → 302 (login)" "302" \
  "$(status "$BASE/schedule/structure/" "$J_ANON")"
check_eq "registrar: структура → 200 (все вошедшие)" "200" \
  "$(status "$BASE/schedule/structure/" "$J_REG")"
STRUCT=$(body "$BASE/schedule/structure/" "$J_ADMIN")
check_contains "структура: отдел" "$STRUCT" "Терапевтическое отделение"
check_contains "структура: специальность" "$STRUCT" "Терапевт"
check_contains "структура: врач" "$STRUCT" "Орлов"
check_contains "структура: секция «без отдела»" "$STRUCT" "Врачи без отдела"
check_contains "ссылка «Структура» в хабе" \
  "$(body "$BASE/schedule/" "$J_ADMIN")" "/schedule/structure/"

SPEC_PAGE=$(body "$BASE/schedule/specialties/" "$J_ADMIN")
check_contains "специальности: врач закреплён" "$SPEC_PAGE" "Орлов"
check_contains "специальности: колонка «Отделы»" "$SPEC_PAGE" "Отделы"
check_contains "специальности: расширенный набор (Хирург)" "$SPEC_PAGE" "Хирург"
check_contains "отделы: колонка «Специальности»" \
  "$(body "$BASE/schedule/departments/" "$J_ADMIN")" "Специальности"
DEPTS_ALL=$(body "$BASE/schedule/departments/" "$J_ADMIN")
check_contains "отделы: новое отделение есть" "$DEPTS_ALL" "Хирургическое отделение"
check_contains "структура: новое отделение с хирургом" \
  "$(body "$BASE/schedule/structure/" "$J_ADMIN")" "Хирургическое отделение"

# комбинированный фильтр списка врачей
THERA_PK=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.schedule.models import Department; print(Department.objects.get(name='Терапевтическое отделение').pk)" \
  2>/dev/null | tail -n1)
THERA_SPEC_PK=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.schedule.models import Specialty; print(Specialty.objects.get(name='Терапевт').pk)" \
  2>/dev/null | tail -n1)
KAR_SPEC_PK=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.schedule.models import Specialty; print(Specialty.objects.get(name='Кардиолог').pk)" \
  2>/dev/null | tail -n1)
DOCS_SPEC=$(body "$BASE/schedule/doctors/?specialty=${THERA_SPEC_PK}" "$J_ADMIN")
check_contains "врачи ?specialty=: Орлов виден" "$DOCS_SPEC" "Орлов"
check_eq "врачи ?specialty=: Каримов скрыт" "0" \
  "$(echo "$DOCS_SPEC" | grep -c 'Каримов')"
check_eq "врачи ?department=&specialty= (комбо) → 200" "200" \
  "$(status "$BASE/schedule/doctors/?department=${THERA_PK}&specialty=${THERA_SPEC_PK}" "$J_ADMIN")"

# валидация сочетания «специальность ↔ отдел»
DOC1_PK=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.schedule.models import Doctor; print(Doctor.objects.get(user__username='doctor1').pk)" \
  2>/dev/null | tail -n1)
DOC1_CAB=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.schedule.models import Doctor; print(Doctor.objects.get(user__username='doctor1').cabinet_id or '')" \
  2>/dev/null | tail -n1)
BAD_EDIT=$(post "$BASE/schedule/doctors/${DOC1_PK}/edit/" "$J_ADMIN" \
  --data-urlencode "existing_user=" \
  --data-urlencode "specialty=${KAR_SPEC_PK}" \
  --data-urlencode "department=${THERA_PK}" \
  --data-urlencode "cabinet=${DOC1_CAB}" \
  --data-urlencode "is_active=on")
check_eq "несочетаемая пара → 200 с ошибкой" "200" "${BAD_EDIT%%|*}"
BAD_BODY=$(post_body "$BASE/schedule/doctors/${DOC1_PK}/edit/" "$J_ADMIN" \
  --data-urlencode "existing_user=" \
  --data-urlencode "specialty=${KAR_SPEC_PK}" \
  --data-urlencode "department=${THERA_PK}" \
  --data-urlencode "cabinet=${DOC1_CAB}" \
  --data-urlencode "is_active=on")
check_contains "текст ошибки валидации" "$BAD_BODY" "не входит"
check_eq "врач не изменён при ошибке" "Терапевт" \
  "$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
    "from apps.schedule.models import Doctor; print(Doctor.objects.get(user__username='doctor1').specialty.name)" \
    2>/dev/null | tail -n1)"
# текущие значения полей карточки — передаём их в удачный edit,
# чтобы смоук не затирал демо-стаж/био (поля формы без передачи обнуляются)
DOC1_EXP=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.schedule.models import Doctor; d=Doctor.objects.get(user__username='doctor1'); print(d.experience_years if d.experience_years is not None else '')" \
  2>/dev/null | tail -n1)
DOC1_BIO=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.schedule.models import Doctor; print(Doctor.objects.get(user__username='doctor1').bio)" \
  2>/dev/null | tail -n1)
GOOD_EDIT=$(post "$BASE/schedule/doctors/${DOC1_PK}/edit/" "$J_ADMIN" \
  --data-urlencode "existing_user=" \
  --data-urlencode "specialty=${THERA_SPEC_PK}" \
  --data-urlencode "department=${THERA_PK}" \
  --data-urlencode "cabinet=${DOC1_CAB}" \
  --data-urlencode "experience_years=${DOC1_EXP}" \
  --data-urlencode "bio=${DOC1_BIO}" \
  --data-urlencode "is_active=on")
check_eq "сочетаемая пара → 302" "302" "${GOOD_EDIT%%|*}"

# отчёты: разрез по специальности
RSPEC=$(body "$BASE/reports/load/?from=${P_FROM}&to=${P_TO}&specialty=${KAR_SPEC_PK}" "$J_ADMIN")
check_contains "отчёт ?specialty=: строка Каримова" "$RSPEC" "text-muted small\">(Кардиолог)"
check_eq "отчёт ?specialty=: Орлов без строки" "0" \
  "$(echo "$RSPEC" | grep -c 'text-muted small\">(Терапевт)')"
check_eq "doctor: селектор специальности скрыт" "0" \
  "$(body "$BASE/reports/" "$J_DOC1" | grep -c 'name="specialty"')"

echo "== 16. Каталог врачей и карточка (без входа) =="
check_eq "аноним: каталог /doctors/ → 200" "200" \
  "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/doctors/")"
DIR_PAGE=$(curl -s "$BASE/doctors/")
check_contains "каталог: активный врач виден" "$DIR_PAGE" "Орлов"
check_contains "каталог: фильтр ?department= (терапевт виден)" \
  "$(curl -s "$BASE/doctors/?department=${THERA_PK}")" "Орлов"
check_eq "каталог: фильтр ?department= (кардиолог скрыт)" "0" \
  "$(curl -s "$BASE/doctors/?department=${THERA_PK}" | grep -c 'Каримов')"

check_eq "аноним: карточка → 200" "200" \
  "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/doctors/${DOC1_PK}/")"
DOC1_CARD=$(curl -s "$BASE/doctors/${DOC1_PK}/")
check_contains "карточка: специальность" "$DOC1_CARD" "Терапевт"
check_contains "карточка: отдел" "$DOC1_CARD" "Терапевтическое отделение"
check_contains "карточка: кабинет и этаж" "$DOC1_CARD" "101"
check_contains "карточка: расписание (Понедельник)" "$DOC1_CARD" "Понедельник"
check_contains "карточка: кнопка «Записаться» ведёт в публичную форму" \
  "$DOC1_CARD" "/request/?specialty="
check_eq "аноним: несуществующий врач → 404" "404" \
  "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/doctors/99999/")"
check_eq "аноним: CRUD врачей закрыт → 302" "302" \
  "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/schedule/doctors/")"
check_contains "логин: ссылка на каталог врачей" \
  "$(curl -s "$BASE/accounts/login/")" "Каталог врачей"

# стаж и био из seeds — смотрим на doctor2 (doctor1 редактируется в смоуке)
DOC2_PK=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.schedule.models import Doctor; print(Doctor.objects.get(user__username='doctor2').id)" \
  2>/dev/null | tail -n1)
DOC2_CARD=$(curl -s "$BASE/doctors/${DOC2_PK}/")
check_contains "карточка: стаж из seeds" "$DOC2_CARD" "12 лет"
check_contains "карточка: био [demo]" "$DOC2_CARD" "Консультирует"

# врачи кликабельны на существующих страницах
check_contains "структура: врач — ссылка на карточку" \
  "$(body "$BASE/schedule/structure/" "$J_ADMIN")" 'href="/doctors/'
check_contains "этажи: врач — ссылка на карточку" \
  "$(body "$BASE/schedule/floors/" "$J_ADMIN")" 'href="/doctors/'
check_contains "специальности: врач — ссылка на карточку" \
  "$(body "$BASE/schedule/specialties/" "$J_ADMIN")" 'href="/doctors/'

# загрузка фото (multipart) на тестовом враче
head -c 256 /dev/urandom > "$COOKIES/photo.png"
UP=$(post_file "$BASE/schedule/doctors/${DOC_TEST_ID}/edit/" "$J_ADMIN" \
  "$COOKIES/photo.png" \
  "existing_user=" "specialty=${SPEC_ID}" "department=" "cabinet=" "is_active=on")
check_eq "фото: multipart-загрузка → 302" "302" "${UP%%|*}"
check_contains "фото: карточка отдаёт /media/doctors/" \
  "$(curl -s "$BASE/doctors/${DOC_TEST_ID}/")" "/media/doctors/"

echo "== 17. Направления к подходящему врачу =="
# --- setup: второй врач той же специальности (для проверки ранжирования) ---
TOM_DATE=$(date -d "+1 day" +%F)
TOM_WD=$(date -d "+1 day" +%u)
: > "$J_ADMIN"; login admin admin12345 "$J_ADMIN"
post "$BASE/schedule/doctors/new/" "$J_ADMIN" \
  --data-urlencode "existing_user=" \
  --data-urlencode "username=doctor_test2" \
  --data-urlencode "password=Doctor-2026!" \
  --data-urlencode "first_name=Тест" \
  --data-urlencode "last_name=Второв" \
  --data-urlencode "specialty=${SPEC_ID}" \
  --data-urlencode "cabinet=" \
  --data-urlencode "is_active=on" > /dev/null
# расписание обоих тест-врачей на завтра: у doctor_test2 слот раньше (08:00)
post "$BASE/schedule/work-schedules/new/" "$J_ADMIN" \
  --data-urlencode "doctor=${DOC_TEST_ID}" --data-urlencode "weekday=${TOM_WD}" \
  --data-urlencode "start_time=10:00" --data-urlencode "end_time=12:00" \
  --data-urlencode "slot_minutes=30" --data-urlencode "valid_from=" --data-urlencode "valid_to=" > /dev/null
DOC_TEST2_ID=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.schedule.models import Doctor; print(Doctor.objects.get(user__username='doctor_test2').id)" \
  2>/dev/null | tail -n1)
post "$BASE/schedule/work-schedules/new/" "$J_ADMIN" \
  --data-urlencode "doctor=${DOC_TEST2_ID}" --data-urlencode "weekday=${TOM_WD}" \
  --data-urlencode "start_time=08:00" --data-urlencode "end_time=09:00" \
  --data-urlencode "slot_minutes=30" --data-urlencode "valid_from=" --data-urlencode "valid_to=" > /dev/null
# направление от врача: свой приём APT2_ID (пациент PAT)
check_eq "аноним: направления → 302 (login)" "302" \
  "$(status "$BASE/appointments/directions/" "$J_ANON")"
check_eq "врач: форма направления по своему приёму → 200" "200" \
  "$(status "$BASE/appointments/directions/new/?appointment=${APT2_ID}" "$J_DOC1")"
CREATE_A=$(post "$BASE/appointments/directions/new/?appointment=${APT2_ID}" "$J_DOC1" \
  --data-urlencode "appointment=${APT2_ID}" \
  --data-urlencode "specialty=${SPEC_ID}" \
  --data-urlencode "reason=[test] направление на гастроэнтеролога")
check_eq "врач: направление уходит в регистратуру (redirect → список)" \
  "$BASE/appointments/directions/" "${CREATE_A#*|}"
check_contains "кабинет: кнопка «Направить» на приёме" \
  "$(body "$BASE/queue/cabinet/?date=${BOOK_DATE}" "$J_DOC1")" "directions/new/?appointment="

# направление администратора с карточки пациента (специальность без врачей):
# в seeds все специальности закреплены за врачами — берём тестовую
EMPTY_SPEC_PK=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.schedule.models import Specialty; print(Specialty.objects.get_or_create(name='Нейрохирург [test]', defaults={'code': 'NEY'})[0].pk)" \
  2>/dev/null | tail -n1)
B_PAT=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.patients.models import Patient; print(Patient.objects.filter(notes__startswith='[demo]', is_active=True).first().id)" \
  2>/dev/null | tail -n1)
check_eq "админ: направление с карточки пациента → 302" "302" \
  "$(post "$BASE/appointments/directions/new/?patient=${B_PAT}" "$J_ADMIN" \
    --data-urlencode "patient=${B_PAT}" \
    --data-urlencode "specialty=${EMPTY_SPEC_PK}" \
    --data-urlencode "reason=[test] направление без врачей" | cut -d'|' -f1)"

# видимость: регистратор — все, врач — только свои, руководство — read-only
DIR_LIST=$(body "$BASE/appointments/directions/" "$J_REG")
check_contains "регистратор видит направление врача" \
  "$DIR_LIST" "[test] направление на гастроэнтеролога"
check_contains "регистратор видит кандидатов (ближайший слот)" \
  "$DIR_LIST" "ближайший слот"
check_contains "кандидат: второй тест-врач подобран" "$DIR_LIST" "Второв"
# ссылки «Записать»: одна на каждого подобранного кандидата каждой новой
# направления (самих врачей может становиться больше — ожидание считаем
# тем же кодом, что и страница)
EXP_LINKS=$(cd "$BASE_DIR" && "$PY" manage.py shell -c "
from apps.appointments.models import Direction
from apps.appointments.routing import find_candidates
print(sum(len(find_candidates(d.specialty))
          for d in Direction.objects.filter(status='new')))
" 2>/dev/null | tail -n1)
check_eq "кнопки «Записать» ведут в запись с direction=" "$EXP_LINKS" \
  "$(echo "$DIR_LIST" | grep -c 'direction=')"
DIR_D1=$(body "$BASE/appointments/directions/" "$J_DOC1")
check_contains "врач: своё направление в списке" \
  "$DIR_D1" "[test] направление на гастроэнтеролога"
check_eq "врач: чужое направление скрыто" "0" \
  "$(echo "$DIR_D1" | grep -c '\[test\] направление без врачей')"
check_eq "руководство: список → 200" "200" \
  "$(status "$BASE/appointments/directions/" "$J_MGR")"
check_eq "руководство: кнопок записи нет (read-only)" "0" \
  "$(body "$BASE/appointments/directions/" "$J_MGR" | grep -c 'direction=')"

# ранжирование: ближайший слот первым (независимый пересчёт ключа)
check_eq "порядок кандидатов: ближайший слот первым" "ok" \
  "$(cd "$BASE_DIR" && "$PY" manage.py shell -c "
from datetime import datetime, timedelta
from django.utils import timezone
from apps.appointments.routing import find_candidates
from apps.appointments.slots import generate_slots
from apps.schedule.models import Doctor, Specialty
spec = Specialty.objects.get(name='Гастроэнтеролог')
def first_dt(doc):
    today = timezone.localdate()
    for off in range(7):
        day = today + timedelta(days=off)
        free = [s for s in generate_slots(doc, day) if not s['busy'] and not s['past']]
        if free:
            return datetime.combine(day, free[0]['time'])
    return datetime.max
actual = [c['doctor'].user.username for c in find_candidates(spec)]
expected = sorted(actual, key=lambda u: first_dt(Doctor.objects.get(user__username=u)))
print('ok' if actual == expected else 'bad')
" 2>/dev/null | tail -n1)"

# запись по направлению: страница, POST, статус
A_PK=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.appointments.models import Direction; d=Direction.objects.filter(reason__startswith='[test] направление на гастро').first(); print(d.pk if d else '')" \
  2>/dev/null | tail -n1)
A_PAT=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.appointments.models import Direction; print(Direction.objects.get(pk=${A_PK}).patient_id)" \
  2>/dev/null | tail -n1)
check_contains "запись по направлению: баннер и предзаполнение" \
  "$(body "$BASE/appointments/booking/?patient=${A_PAT}&specialty=${SPEC_ID}&doctor=${DOC_TEST2_ID}&date=${TOM_DATE}&direction=${A_PK}" "$J_REG")" \
  "Оформляется по направлению"
check_eq "запись по направлению → 302" "302" \
  "$(post "$BASE/appointments/booking/" "$J_REG" \
    --data-urlencode "patient=${A_PAT}" \
    --data-urlencode "doctor=${DOC_TEST2_ID}" \
    --data-urlencode "visit_date=${TOM_DATE}" \
    --data-urlencode "slot_start=08:00:00" \
    --data-urlencode "visit_type=primary" \
    --data-urlencode "comment=[test] запись по направлению" \
    --data-urlencode "direction=${A_PK}" | cut -d'|' -f1)"
check_eq "направление закрыто записью (статус)" "booked" \
  "$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
    "from apps.appointments.models import Direction; print(Direction.objects.get(pk=${A_PK}).status)" \
    2>/dev/null | tail -n1)"
check_eq "направление связано с записью" "1" \
  "$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
    "from apps.appointments.models import Direction; d=Direction.objects.get(pk=${A_PK}); print(1 if d.appointment_id else 0)" \
    2>/dev/null | tail -n1)"

# без врачей нужной специальности + отмена + отказы по ролям
check_contains "специальность без врачей: подсказка" "$DIR_LIST" "Подходящих врачей не найдено"
B_PK=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.appointments.models import Direction; d=Direction.objects.filter(reason__startswith='[test] направление без врачей').first(); print(d.pk if d else '')" \
  2>/dev/null | tail -n1)
check_eq "регистратор: отмена направления → 302" "302" \
  "$(post "$BASE/appointments/directions/${B_PK}/cancel/" "$J_REG" | cut -d'|' -f1)"
check_eq "направление отменено (статус)" "cancelled" \
  "$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
    "from apps.appointments.models import Direction; print(Direction.objects.get(pk=${B_PK}).status)" \
    2>/dev/null | tail -n1)"
# регистрар не выписывает направления — уводит на дашборд
check_eq "регистратор: создание направления заблокировано (редирект на дашборд)" \
  "$BASE/" \
  "$(post "$BASE/appointments/directions/new/" "$J_REG" \
    --data-urlencode "patient=${B_PAT}" \
    --data-urlencode "specialty=${EMPTY_SPEC_PK}" \
    --data-urlencode "reason=[test] не должна создаться" | cut -d'|' -f2)"
# врач не направляет по чужому приёму
OTHER_APPT=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.appointments.models import Appointment; a=Appointment.objects.exclude(doctor__user__username='doctor1').first(); print(a.pk if a else '')" \
  2>/dev/null | tail -n1)
check_contains "врач: чужой приём → отказ (в кабинет)" \
  "$(post "$BASE/appointments/directions/new/?appointment=${OTHER_APPT}" "$J_DOC1" \
    --data-urlencode "appointment=${OTHER_APPT}" \
    --data-urlencode "specialty=${SPEC_ID}" \
    --data-urlencode "reason=[test] чужой приём" | cut -d'|' -f2)" \
  "/queue/cabinet/"

echo "== 18. Публичная заявка пациента (без входа) =="
# идемпотентность: подчищаем артефакты прошлых прогонов,
# иначе дедуп найдёт старую карточку и проверки created=1 сломаются
(cd "$BASE_DIR" && "$PY" manage.py shell -c "
from apps.appointments.models import Direction
from apps.patients.models import Patient
Direction.objects.filter(
    reason__startswith='[test] заявка с сайта',
).delete()
Direction.objects.filter(
    reason__startswith='[test] дедуп ФИО+ДР',
).delete()
Patient.objects.filter(last_name='Сайтов', first_name='Пациент').delete()
" > /dev/null 2>&1)

check_eq "аноним: /request/ → 200" "200" "$(status "$BASE/request/" "$J_ANON")"
REQ_PAGE=$(body "$BASE/request/" "$J_ANON")
check_contains "форма: поле ФИО" "$REQ_PAGE" "id_last_name"
check_eq "форма: поля СНИЛС нет" "0" "$(echo "$REQ_PAGE" | grep -c 'id_snils')"
check_eq "форма: поля Email нет" "0" "$(echo "$REQ_PAGE" | grep -c 'id_email')"
check_contains "форма: специальность" "$REQ_PAGE" "id_specialty"
check_contains "форма: honeypot скрыт" "$REQ_PAGE" "id_website"
check_contains "навбар: ссылка «Запись»" "$REQ_PAGE" "/request/"
check_contains "лендинг: кнопка «Записаться онлайн»" \
  "$(body "$BASE/" "$J_ANON")" "/request/"

# невалидная заявка: ничего не создаёт
PT_BEFORE=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from django.contrib.auth.models import User; from apps.patients.models import Patient; print(Patient.objects.count())" \
  2>/dev/null | tail -n1)
DIR_BEFORE=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.appointments.models import Direction; print(Direction.objects.count())" \
  2>/dev/null | tail -n1)
BAD=$(post "$BASE/request/" "$J_ANON" \
  --data-urlencode "last_name=Плохой" --data-urlencode "first_name=Клиент" \
  --data-urlencode "birth_date=2031-01-01" --data-urlencode "gender=" \
  --data-urlencode "phone=12" \
  --data-urlencode "specialty=${SPEC_ID}" --data-urlencode "reason=spam" \
  --data-urlencode "website=")
check_eq "невалидная заявка → 200 (ошибки на месте)" "200" "${BAD%%|*}"
check_eq "невалидная: пациентов не прибавилось" "$PT_BEFORE" \
  "$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
    "from apps.patients.models import Patient; print(Patient.objects.count())" \
    2>/dev/null | tail -n1)"
check_eq "невалидная: направлений не прибавилось" "$DIR_BEFORE" \
  "$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
    "from apps.appointments.models import Direction; print(Direction.objects.count())" \
    2>/dev/null | tail -n1)"

# honeypot: бот заполнил скрытое поле
BAD_HP=$(post "$BASE/request/" "$J_ANON" \
  --data-urlencode "last_name=Бот" --data-urlencode "first_name=Спам" \
  --data-urlencode "birth_date=1990-01-01" --data-urlencode "gender=M" \
  --data-urlencode "phone=+998 90 000-00-00" \
  --data-urlencode "specialty=${SPEC_ID}" --data-urlencode "reason=bot" \
  --data-urlencode "website=http://spam.example")
check_eq "honeypot: пациентов не прибавилось" "$PT_BEFORE" \
  "$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
    "from apps.patients.models import Patient; print(Patient.objects.count())" \
    2>/dev/null | tail -n1)"
check_eq "honeypot: направлений не прибавилось" "$DIR_BEFORE" \
  "$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
    "from apps.appointments.models import Direction; print(Direction.objects.count())" \
    2>/dev/null | tail -n1)"

# валидная заявка
OK=$(post "$BASE/request/" "$J_ANON" \
  --data-urlencode "last_name=Сайтов" --data-urlencode "first_name=Пациент" \
  --data-urlencode "patronymic=Петрович" \
  --data-urlencode "birth_date=1988-11-11" --data-urlencode "gender=M" \
  --data-urlencode "phone=+998 90 777-88-99" \
  --data-urlencode "specialty=${SPEC_ID}" \
  --data-urlencode "reason=[test] заявка с сайта")
check_eq "валидная заявка → 302" "302" "${OK%%|*}"
REQ_LOC="${OK#*|}"
check_contains "редирект ведёт на /p/<uuid>/?new=" "$REQ_LOC" "/p/"
check_contains "редирект содержит new=" "$REQ_LOC" "new="
REQ_UUID=$(echo "$REQ_LOC" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -n1)
check_eq "формат UUID в редиректе" "1" \
  "$(echo "$REQ_UUID" | grep -cE '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')"
REQ_PK=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.appointments.models import Direction; d=Direction.objects.filter(reason='[test] заявка с сайта').order_by('-pk').first(); print(d.pk if d else '')" \
  2>/dev/null | tail -n1)
check_eq "направление создано" "ok" "$([ -n "$REQ_PK" ] && echo ok || echo no)"
check_eq "направление: created_by IS NULL (маркер «с сайта»)" "1" \
  "$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
    "from apps.appointments.models import Direction; d=Direction.objects.get(pk=${REQ_PK}); print(1 if d.created_by_id is None and d.status=='new' else 0)" \
    2>/dev/null | tail -n1)"

# страница пациента: баннер + подобранные врачи
# (нужен полный URL — баннер включается параметром ?new=)
REQ_PAGE2=$(body "$REQ_LOC" "$J_ANON")
check_contains "баннер: номер заявки" "$REQ_PAGE2" "Н-"
check_contains "баннер: причина" "$REQ_PAGE2" "[test] заявка с сайта"
check_contains "баннер: карточка создана" "$REQ_PAGE2" "Карточка пациента создана"
check_contains "баннер: подбор врачей" "$REQ_PAGE2" "подобрала"
check_contains "баннер: карточки врачей со слотами" "$REQ_PAGE2" "ближайший слот"

# чужое направление по UUID не показывается
OTHER_DIR=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.appointments.models import Direction; d=Direction.objects.exclude(pk=${REQ_PK}).order_by('-pk').first(); print(d.pk if d else '')" \
  2>/dev/null | tail -n1)
check_eq "чужое направление игнорируется" "0" \
  "$(body "${REQ_LOC%%\?*}?new=${OTHER_DIR}" "$J_ANON" | grep -c 'принята')"

# дедуп: тот же человек (ФИО+ДР, регистр кириллицы) -> новая карточка НЕ создана
PT_BEFORE2=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.patients.models import Patient; print(Patient.objects.count())" \
  2>/dev/null | tail -n1)
DEDUP=$(post "$BASE/request/" "$J_ANON" \
  --data-urlencode "last_name=САЙТОВ" --data-urlencode "first_name=пациЕНТ" \
  --data-urlencode "patronymic=" \
  --data-urlencode "birth_date=1988-11-11" --data-urlencode "gender=M" \
  --data-urlencode "phone=+998 90 000-11-22" \
  --data-urlencode "specialty=${SPEC_ID}" \
  --data-urlencode "reason=[test] дедуп ФИО+ДР")
check_contains "дедуп: редирект с created=0" "${DEDUP#*|}" "created=0"
check_eq "дедуп: пациентов не прибавилось" "$PT_BEFORE2" \
  "$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
    "from apps.patients.models import Patient; print(Patient.objects.count())" \
    2>/dev/null | tail -n1)"
check_contains "дедуп: сообщение «существующая карточка»" \
  "$(body "${DEDUP#*|}" "$J_ANON")" \
  "Найдена существующая карточка"

# регистратор видит заявку с сайта
login registrar1 registrar12345 "$J_REG"
check_contains "направления: бейдж «Заявка с сайта»" \
  "$(body "$BASE/appointments/directions/" "$J_REG")" "Заявка с сайта"

# код заявки: кнопка копирования на странице результата
check_contains "страница заявки: кнопка «Скопировать код заявки»" \
  "$REQ_PAGE2" "Скопировать код заявки"
check_contains "страница заявки: код равен public_id" "$REQ_PAGE2" "$REQ_UUID"
check_contains "страница: кнопка есть и без баннера" \
  "$(body "${REQ_LOC%%\?*}" "$J_ANON")" "Скопировать код заявки"
check_contains "страница: JS-обработчик копирования" "$REQ_PAGE2" "js-copy-code"

# блок «Мои записи» на главной: ввод кода
LANDING=$(body "$BASE/" "$J_ANON")
check_contains "лендинг: поле ввода кода" "$LANDING" 'name="code"'
check_contains "лендинг: кнопка «Открыть»" "$LANDING" "Открыть"
check_eq "код: канонический UUID → /p/<uuid>/" "$BASE/p/${REQ_UUID}/" \
  "$(redirect "$BASE/?code=${REQ_UUID}" "$J_ANON")"
check_eq "код: без дефисов → /p/<uuid>/" "$BASE/p/${REQ_UUID}/" \
  "$(redirect "$BASE/?code=${REQ_UUID//-/}" "$J_ANON")"
check_eq "код: в верхнем регистре → /p/<uuid>/" "$BASE/p/${REQ_UUID}/" \
  "$(redirect "$BASE/?code=$(printf '%s' "$REQ_UUID" | tr '[:lower:]' '[:upper:]')" "$J_ANON")"
check_eq "код: скопированная ссылка /p/<uuid>/ → /p/<uuid>/" "$BASE/p/${REQ_UUID}/" \
  "$(curl -s -o /dev/null -w '%{redirect_url}' -G \
      --data-urlencode "code=$BASE/p/${REQ_UUID}/" "$BASE/")"
BAD_CODE_PAGE=$(body "$BASE/?code=not-a-code" "$J_ANON")
check_contains "код: мусор → понятная ошибка" "$BAD_CODE_PAGE" "Код не найден"
check_contains "код: введённое значение сохранено" "$BAD_CODE_PAGE" 'value="not-a-code"'
check_contains "код: неизвестный UUID → ошибка" \
  "$(body "$BASE/?code=00000000-0000-4000-8000-000000000000" "$J_ANON")" \
  "Код не найден"
check_eq "вошедший: ?code не перехватывает главную" "200" \
  "$(status "$BASE/?code=${REQ_UUID}" "$J_REG")"

# карточка врача анониму ведёт на публичную форму
DOC1_PK=$(cd "$BASE_DIR" && "$PY" manage.py shell -c \
  "from apps.schedule.models import Doctor; print(Doctor.objects.get(user__username='doctor1').pk)" \
  2>/dev/null | tail -n1)
check_contains "карточка врача: кнопка ведёт на /request/" \
  "$(body "$BASE/doctors/${DOC1_PK}/" "$J_ANON")" "/request/?specialty="

echo
echo "=================================="
echo "Итого: PASS=$PASS FAIL=$FAIL"
echo "=================================="
[ "$FAIL" -eq 0 ]
