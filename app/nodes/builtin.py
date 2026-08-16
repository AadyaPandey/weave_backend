import asyncio
import json
import re
import smtplib
import ssl
from email.utils import formataddr, parseaddr

import httpx

from .base import BaseNode
from ..config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USE_TLS,
)


def resolve(value, context):
    if isinstance(value, dict):
        return {key: resolve(item, context) for key, item in value.items()}

    if isinstance(value, list):
        return [resolve(item, context) for item in value]

    if not isinstance(value, str):
        return value

    pattern = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")

    def get_value(path):
        current = context

        for key in path.split("."):
            current = current.get(key, "") if isinstance(current, dict) else ""

        return current

    matches = list(pattern.finditer(value))

    if len(matches) == 1 and matches[0].span() == (0, len(value)):
        return get_value(matches[0].group(1))

    return pattern.sub(lambda match: str(get_value(match.group(1))), value)


class Manual(BaseNode):
    async def execute(self, input_data, config, context):
        return input_data


class Text(BaseNode):
    async def execute(self, input_data, config, context):
        return {
            "text": resolve(config.get("text", ""), context),
        }


class JSONInput(BaseNode):
    async def execute(self, input_data, config, context):
        value = resolve(config.get("value", {}), context)

        return json.loads(value) if isinstance(value, str) else value


class LLM(BaseNode):
    async def execute(self, input_data, config, context):
        prompt = resolve(config.get("prompt", ""), context)

        if not GROQ_API_KEY:
            return {
                "output": f"[MOCK LLM] {prompt}",
                "mock": True,
            }

        from groq import AsyncGroq

        response = await AsyncGroq(api_key=GROQ_API_KEY).chat.completions.create(
            model=config.get("model", GROQ_MODEL),
            messages=[
                {
                    "role": "user",
                    "content": str(prompt),
                }
            ],
            temperature=float(config.get("temperature", 0.2)),
        )

        return {
            "output": response.choices[0].message.content,
            "mock": False,
        }


class HTTP(BaseNode):
    async def execute(self, input_data, config, context):
        method = config.get("method", "GET").upper()
        url = resolve(config.get("url", ""), context)
        headers = resolve(config.get("headers", {}), context)
        body = resolve(config.get("body", {}), context)

        async with httpx.AsyncClient(
            timeout=float(config.get("timeout", 20))
        ) as client:
            response = await client.request(
                method,
                url,
                headers=headers,
                json=None if method in ("GET", "HEAD") else body,
            )

        try:
            data = response.json()
        except Exception:
            data = response.text

        return {
            "status_code": response.status_code,
            "data": data,
        }


class Weather(BaseNode):
    async def execute(self, input_data, config, context):
        city = resolve(
            config.get(
                "city",
                context.get("city", "") if isinstance(context, dict) else "",
            ),
            context,
        )

        latitude = resolve(config.get("latitude"), context)
        longitude = resolve(config.get("longitude"), context)

        async with httpx.AsyncClient(
            timeout=float(config.get("timeout", 20))
        ) as client:
            if latitude in (None, "") or longitude in (None, ""):
                if not city:
                    raise ValueError(
                        "Weather node needs a city, or latitude and longitude."
                    )

                geocoding_response = await client.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={
                        "name": city,
                        "count": 1,
                        "language": "en",
                        "format": "json",
                    },
                )

                geocoding_response.raise_for_status()

                results = geocoding_response.json().get("results", [])

                if not results:
                    raise ValueError(f"Location not found: {city}")

                place = results[0]
                latitude = place["latitude"]
                longitude = place["longitude"]
                city = place["name"]

            weather_response = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": (
                        "temperature_2m,weather_code,"
                        "wind_speed_10m,precipitation"
                    ),
                    "timezone": "auto",
                },
            )

            weather_response.raise_for_status()
            current = weather_response.json()["current"]

        labels = {
            0: "Clear sky",
            1: "Mostly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Fog",
            48: "Rime fog",
            51: "Light drizzle",
            53: "Drizzle",
            55: "Heavy drizzle",
            61: "Light rain",
            63: "Rain",
            65: "Heavy rain",
            71: "Light snow",
            73: "Snow",
            75: "Heavy snow",
            80: "Rain showers",
            81: "Rain showers",
            82: "Heavy showers",
            95: "Thunderstorm",
        }

        weather_code = current["weather_code"]

        return {
            "location": city or f"{latitude}, {longitude}",
            "temperature_c": current["temperature_2m"],
            "weather_code": weather_code,
            "description": labels.get(weather_code, "Unknown conditions"),
            "wind_speed_kmh": current["wind_speed_10m"],
            "precipitation_mm": current["precipitation"],
            "is_good": (
                weather_code in (0, 1, 2)
                and current["precipitation"] == 0
            ),
        }


class Email(BaseNode):
    async def execute(self, input_data, config, context):
        sender = resolve(config.get("sender_email", ""), context)
        password = resolve(config.get("app_password", ""), context)
        recipient = resolve(config.get("to", ""), context)
        body = resolve(config.get("body", ""), context)
        # Subjects are generated from the resolved email body. This keeps the
        # subject out of the browser-side node configuration.
        subject = await self._generate_subject(body)

        host = SMTP_HOST
        port = SMTP_PORT
        use_tls = SMTP_USE_TLS

        sender_name, sender_address = parseaddr(str(sender))
        _, recipient_address = parseaddr(str(recipient))

        if not sender_address or sender_address != str(sender):
            raise ValueError("Email node needs a valid sender_email.")

        if not recipient_address or recipient_address != str(recipient):
            raise ValueError("Email node needs a valid recipient email address.")

        if not isinstance(password, str) or not password.strip():
            raise ValueError("Email node needs an app_password for this send.")

        if not isinstance(host, str) or not host.strip():
            raise ValueError("Email node needs a valid SMTP host.")

        try:
            port = int(port)
        except (TypeError, ValueError):
            raise ValueError("Email node needs a valid SMTP port.")

        if not 1 <= port <= 65535:
            raise ValueError("Email node needs a valid SMTP port.")

        if "\n" in str(subject) or "\r" in str(subject):
            raise ValueError("Email subject cannot contain line breaks.")

        message = (
            f"From: {formataddr((sender_name, sender_address))}\r\n"
            f"To: {recipient_address}\r\n"
            f"Subject: {subject}\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n\r\n"
            f"{body}"
        )

        def send_email():
            with smtplib.SMTP(host, port, timeout=20) as server:
                if use_tls:
                    server.starttls(context=ssl.create_default_context())

                server.login(sender_address, password)

                server.sendmail(
                    sender_address,
                    [recipient_address],
                    message.encode("utf-8"),
                )

        await asyncio.to_thread(send_email)

        return {
            "sent": True,
            "to": recipient_address,
            "subject": str(subject),
        }

    async def _generate_subject(self, body):
        if not GROQ_API_KEY:
            return "Workflow notification"

        from groq import AsyncGroq

        response = await AsyncGroq(api_key=GROQ_API_KEY).chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Write a concise email subject line (10 words or fewer) "
                        "for the following email. Return only the subject line.\n\n"
                        f"{body}"
                    ),
                }
            ],
            temperature=0.2,
        )
        subject = response.choices[0].message.content.strip().splitlines()[0]
        return subject or "Workflow notification"


class Condition(BaseNode):
    async def execute(self, input_data, config, context):
        left = resolve(config.get("left"), context)
        right = resolve(config.get("right"), context)
        operator = config.get("operator", "equals")

        if operator == "equals":
            result = left == right
        elif operator == "not_equals":
            result = left != right
        elif operator == "contains":
            result = str(right) in str(left)
        elif operator == "exists":
            result = left not in (None, "", False)
        elif operator == "greater_than":
            result = float(left) > float(right)
        elif operator == "less_than":
            result = float(left) < float(right)
        else:
            raise ValueError("Unsupported operator")

        return {
            "result": result,
            "branch": "true" if result else "false",
            "data": input_data,
        }


class Transform(BaseNode):
    async def execute(self, input_data, config, context):
        operation = config.get("operation", "identity")
        value = resolve(config.get("value", input_data), context)

        if operation == "uppercase":
            return str(value).upper()

        if operation == "lowercase":
            return str(value).lower()

        if operation == "stringify":
            return json.dumps(value)

        if operation == "parse_json":
            return json.loads(value)

        if operation == "pick":
            return value.get(config.get("key"))

        return value


class Response(BaseNode):
    async def execute(self, input_data, config, context):
        return resolve(config.get("value", input_data), context)


NODE_REGISTRY = {
    "manual_trigger": Manual,
    "text": Text,
    "json": JSONInput,
    "llm": LLM,
    "http_request": HTTP,
    "weather": Weather,
    "email": Email,
    "condition": Condition,
    "transform": Transform,
    "response": Response,
}
