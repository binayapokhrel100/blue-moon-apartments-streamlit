import streamlit as st


def _detect_browser(
    user_agent: str,
) -> str:

    value = user_agent.lower()

    if "edg/" in value:
        return "Microsoft Edge"

    if "firefox/" in value:
        return "Firefox"

    if (
        "chrome/" in value
        and "edg/" not in value
    ):
        return "Chrome"

    if (
        "safari/" in value
        and "chrome/" not in value
    ):
        return "Safari"

    return "Unknown Browser"


def _detect_device(
    user_agent: str,
) -> str:

    value = user_agent.lower()

    if "iphone" in value:
        return "iPhone"

    if "ipad" in value:
        return "iPad"

    if "android" in value:
        return "Android Device"

    if "windows" in value:
        return "Windows PC"

    if "macintosh" in value:
        return "Mac"

    if "linux" in value:
        return "Linux Device"

    return "Unknown Device"


def get_client_info() -> dict:

    user_agent = ""
    ip_address = "Unavailable"
    location_label = "Unavailable"

    try:

        headers = st.context.headers

        user_agent = (
            headers.get(
                "User-Agent",
                "",
            )
            or ""
        )

        forwarded_ip = (
            headers.get(
                "X-Forwarded-For"
            )
            or headers.get(
                "X-Real-IP"
            )
        )

        if forwarded_ip:

            ip_address = (
                forwarded_ip
                .split(",")[0]
                .strip()
            )

        else:

            try:

                context_ip = (
                    st.context.ip_address
                )

                if context_ip:
                    ip_address = (
                        context_ip
                    )

            except Exception:
                pass

        location_label = (
            headers.get(
                "CF-IPCity"
            )
            or headers.get(
                "X-Geo-City"
            )
            or "Unavailable"
        )

    except Exception:
        pass

    return {
        "device_name": (
            _detect_device(
                user_agent
            )
        ),
        "browser_name": (
            _detect_browser(
                user_agent
            )
        ),
        "ip_address": ip_address,
        "location_label": (
            location_label
        ),
        "user_agent": user_agent,
    }