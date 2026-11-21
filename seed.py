import asyncio
import psychohelp.models 
from psychohelp.models.appointments import Appointment 
from psychohelp.models.applications import Application

from psychohelp.repositories import hash_password
from psychohelp.repositories.users import create_user
from psychohelp.services.psychologists import create_psychologist

async def seed_db():
    print("Начинаем создание тестовых данных...")
    raw_password = "password123" 
    hashed_pw = hash_password(raw_password)

    try:
        user = await create_user(
            first_name="Анна",
            last_name="Смирнова",
            phone_number="+79998887766",
            email="smirnova_auth@example.com", 
            hashed_password=hashed_pw
        )
        print(f"✅ Шаг 1: Пользователь создан (ID: {user.id})")
        print(f"🔑 Данные для входа -> Email: smirnova_auth@example.com | Пароль: {raw_password}")
        
    except ValueError as e:
        print(f"Ошибка при создании пользователя: {e}")
        return  #

    psychologist_data = {
        "experience": "8 лет",
        "qualification": "Гештальт-терапевт",
        "consult_areas": "Семейные отношения, личностный рост",
        "description": "Помогаю наладить контакт с собой и окружающими.",
        "office": "Онлайн",
        "education": "СПбГУ",
        "short_description": "Эмпатичный и поддерживающий специалист",
    }
    
    created_psychologist = await create_psychologist(
        user_id=user.id, 
        psychologist_data=psychologist_data
    )
    
    print(f"✅ Шаг 2: Психолог успешно создан! (ID психолога: {created_psychologist.id})")
    print("🚀 Всё готово! Теперь можно проверять авторизацию в Swagger.")

if __name__ == "__main__":
    asyncio.run(seed_db())