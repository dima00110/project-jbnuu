# Сущности (ER-диаграмма) — «Регистратура»

## Mermaid ER-диаграмма

```mermaid
erDiagram
    User ||--o{ Doctor : "профиль врача"
    User ||--o{ AuditLog : "события"
    User ||--o{ Appointment : "создал"
    User ||--o{ Consultation : "провёл"

    Patient ||--o{ InsurancePolicy : "имеет"
    Patient ||--o{ Appointment : "записи"
    Patient ||--o{ QueueTicket : "талоны"
    Patient ||--o{ Consultation : "приёмы"

    Specialty ||--o{ Doctor : "специальность"
    Cabinet ||--o{ Doctor : "кабинет"
    Doctor ||--o{ WorkSchedule : "расписание"
    Doctor ||--o{ Appointment : "приём"
    Doctor ||--o{ QueueTicket : "очередь"
    Doctor ||--o{ Consultation : "приёмы"

    Appointment ||--o| QueueTicket : "талон очереди"
    Appointment ||--o{ Consultation : "визиты"

    Patient {
        bigint id PK
        string last_name "Фамилия"
        string first_name "Имя"
        string patronymic "Отчество"
        date birth_date "Дата рождения"
        enum gender "Пол: M/J"
        string snils "СНИЛС (уникален, может быть пустым)"
        string phone "Телефон"
        string email "Email (опц.)"
        string address "Адрес регистрации"
        text notes "Примечания"
        boolean is_active "Мягкое удаление"
        datetime created_at
        datetime updated_at
    }

    InsurancePolicy {
        bigint id PK
        bigint patient_id FK
        enum policy_type "ОМС / ДМС"
        string number "Номер полиса"
        string insurer "Страхователь"
        date valid_from "Действителен с"
        date valid_to "Действителен по"
    }

    User {
        bigint id PK
        string username "Логин"
        string password "Хеш пароля"
        string full_name "ФИО"
        boolean is_active
        bool is_superuser
    }

    Specialty {
        bigint id PK
        string name "Название"
        string code "Код"
    }

    Cabinet {
        bigint id PK
        string number "Номер кабинета"
        int floor "Этаж"
        string building "Корпус"
    }

    Doctor {
        bigint id PK
        bigint user_id FK
        bigint specialty_id FK
        bigint cabinet_id FK
        string phone_ext "Внутренний телефон"
        boolean is_active
    }

    WorkSchedule {
        bigint id PK
        bigint doctor_id FK
        int weekday "1=Пн … 7=Вс"
        time start_time "Начало приёма"
        time end_time "Конец приёма"
        int slot_minutes "Длительность слота"
        date valid_from "Действует с"
        date valid_to "Действует по (опц.)"
    }

    Appointment {
        bigint id PK
        bigint patient_id FK
        bigint doctor_id FK
        bigint created_by_id FK "Кто записал"
        date visit_date "Дата визита"
        time slot_start "Время слота"
        enum visit_type "первичный / повторный"
        enum status "записан, подтверждён, отменён_пациентом, отменён_регистратором, неявка, завершён"
        string cancel_reason "Причина отмены"
        text comment
        datetime created_at
        datetime updated_at
    }

    QueueTicket {
        bigint id PK
        bigint patient_id FK
        bigint appointment_id FK "NULL — талон без записи"
        bigint doctor_id FK
        int number "Номер в очереди за день"
        date issued_date
        enum status "ожидает, вызван, на_приёме, завершён, пропущен"
        datetime issued_at
        datetime called_at "Время вызова"
        int waiting_minutes "Рассчитанное ожидание"
    }

    Consultation {
        bigint id PK
        bigint appointment_id FK
        bigint patient_id FK
        bigint doctor_id FK
        text complaints "Жалобы / анамнез"
        string diagnosis "Диагноз (МКБ-10 опц.)"
        text prescriptions "Назначения"
        text recommendations "Рекомендации"
        date next_visit_date "Следующий визит"
        datetime started_at
        datetime closed_at
        enum status "в_процессе, завершён"
    }

    AuditLog {
        bigint id PK
        bigint user_id FK
        string action "действие"
        string entity_type "сущность"
        bigint entity_id "ID записи"
        json changes "изменения"
        datetime created_at
    }
```

## Ключевые замечания

### Статусы Appointment (запись)
```
записан → подтверждён → завершён
   │          │
   ├→ отменён_пациентом
   ├→ отменён_регистратором
   └→ неявка        (помечает регистратор/врач по факту)
```

### Статусы QueueTicket (талон очереди)
```
ожидает → вызван → на_приёме → завершён
   │         └────→ пропущен (повторный вызов не состоялся)
   └→ пропущен
```

### Связи и правила
- **Appointment.slot_start** уникален в паре `(doctor_id, visit_date, slot_start)` для активных статусов — защита от двойной записи.
- **QueueTicket.appointment_id** может быть `NULL` — пациент пришёл без записи.
- **Consultation** создаётся врачом при открытии приёма; закрытие приёма переводит связанный Appointment в «завершён».
- **Мягкое удаление**: `Patient.is_active = false` вместо физического удаления (сохраняется история визитов).
- **AuditLog** пишется для: создание/изменение/отмена записи, создание пациента, вызов пациента, закрытие приёма.
- Внешние ключи каскадно защищены: `PROTECT` для справочников, `SET_NULL` для опциональных полей.
