import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


# ---------------------------------------------------------
# 1. 페이지 기본 설정
# ---------------------------------------------------------
st.set_page_config(
    page_title="어제의 박스오피스",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 어제의 박스오피스")
st.caption("영화진흥위원회 KOBIS 일별 박스오피스 데이터를 보여 줍니다.")


# ---------------------------------------------------------
# 2. 한국 시간 기준으로 '어제' 날짜 계산
#    Streamlit Cloud 서버는 한국 시간이 아닐 수 있으므로
#    반드시 Asia/Seoul 시간대를 지정합니다.
# ---------------------------------------------------------
KST = ZoneInfo("Asia/Seoul")

now_korea = datetime.now(KST)
yesterday = now_korea.date() - timedelta(days=1)

# API에 보낼 날짜: 20260903 형태
target_dt = yesterday.strftime("%Y%m%d")

# 화면에 보여 줄 날짜: 2026년 09월 03일 형태
display_date = yesterday.strftime("%Y년 %m월 %d일")

st.subheader(f"📅 {display_date} 박스오피스")


# ---------------------------------------------------------
# 3. KOBIS API에서 데이터 가져오기
#
# @st.cache_data(ttl=3600)
# → 같은 날짜의 데이터를 다시 요청할 경우
#   약 1시간 동안 API를 다시 호출하지 않고 저장한 결과를 사용합니다.
# ---------------------------------------------------------
@st.cache_data(ttl=3600)
def load_boxoffice(target_date):
    # Streamlit 비밀 금고에서 API 인증키를 가져옵니다.
    # 코드 안에는 실제 인증키를 직접 적지 않습니다.
    api_key = st.secrets["KOBIS_KEY"]

    url = (
        "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
        "boxoffice/searchDailyBoxOfficeList.json"
    )

    params = {
        "key": api_key,
        "targetDt": target_date
    }

    try:
        # API 요청
        response = requests.get(
            url,
            params=params,
            timeout=10
        )

        # HTTP 요청 자체가 실패한 경우 예외 발생
        response.raise_for_status()

        # JSON 형식으로 변환
        data = response.json()

    except requests.RequestException as e:
        return {
            "success": False,
            "message": (
                "KOBIS 서버에 연결하지 못했습니다.\n\n"
                "다음을 확인해 주세요.\n"
                "- 인터넷 연결 상태\n"
                "- KOBIS API 서버 상태\n"
                "- 요청 주소가 올바른지 여부\n\n"
                f"오류 내용: {e}"
            )
        }

    except ValueError:
        return {
            "success": False,
            "message": (
                "KOBIS 서버에서 올바른 JSON 응답을 받지 못했습니다.\n\n"
                "잠시 후 다시 시도해 주세요."
            )
        }

    # -----------------------------------------------------
    # 인증키가 잘못되어도 HTTP 상태코드는 200일 수 있습니다.
    # 이 경우 JSON 안에 faultInfo가 들어옵니다.
    # -----------------------------------------------------
    if "faultInfo" in data:
        fault = data["faultInfo"]

        message = fault.get("message", "알 수 없는 API 오류입니다.")

        return {
            "success": False,
            "message": (
                "KOBIS API에서 오류를 반환했습니다.\n\n"
                f"오류 메시지: {message}\n\n"
                "다음을 확인해 주세요.\n"
                "- Streamlit secrets에 KOBIS_KEY가 정확히 등록되어 있는지\n"
                "- 발급받은 KOBIS API 인증키가 정상인지\n"
                "- 인증키 앞뒤에 불필요한 공백이 없는지"
            )
        }

    # -----------------------------------------------------
    # 실제 영화 목록 찾기
    # -----------------------------------------------------
    try:
        movies = data["boxOfficeResult"]["dailyBoxOfficeList"]
    except (KeyError, TypeError):
        return {
            "success": False,
            "message": (
                "KOBIS 응답에서 박스오피스 목록을 찾지 못했습니다.\n\n"
                "API 응답 구조가 변경되었거나 일시적인 오류일 수 있습니다."
            )
        }

    # 영화 목록이 비어 있는 경우
    if not movies:
        return {
            "success": False,
            "message": (
                "조회된 영화가 없습니다.\n\n"
                "다음을 확인해 주세요.\n"
                "- 조회 날짜의 박스오피스 집계가 완료되었는지\n"
                "- KOBIS 서비스가 정상적으로 운영 중인지\n"
                "- 날짜 계산이 올바른지"
            )
        }

    # -----------------------------------------------------
    # 필요한 열만 DataFrame으로 만듭니다.
    # -----------------------------------------------------
    df = pd.DataFrame(movies)

    df = df[
        [
            "rank",
            "movieNm",
            "openDt",
            "audiCnt",
            "audiAcc",
            "scrnCnt"
        ]
    ].copy()

    # -----------------------------------------------------
    # KOBIS의 숫자는 문자열로 오므로 실제 숫자로 변환합니다.
    #
    # 그래프나 정렬을 제대로 하려면 반드시 숫자형이어야 합니다.
    # -----------------------------------------------------
    numeric_columns = [
        "rank",
        "audiCnt",
        "audiAcc",
        "scrnCnt"
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    # 숫자로 바뀌지 않은 이상 데이터가 있다면 0으로 처리
    df[numeric_columns] = df[numeric_columns].fillna(0)

    # 순위는 정수로 표시
    df["rank"] = df["rank"].astype(int)

    # 관객수 등의 값도 정수로 사용
    df["audiCnt"] = df["audiCnt"].astype(int)
    df["audiAcc"] = df["audiAcc"].astype(int)
    df["scrnCnt"] = df["scrnCnt"].astype(int)

    # 순위 기준으로 정렬
    df = df.sort_values("rank")

    return {
        "success": True,
        "data": df
    }


# ---------------------------------------------------------
# 4. 데이터 불러오기
# ---------------------------------------------------------
try:
    result = load_boxoffice(target_dt)

except KeyError:
    st.error(
        """
        🔑 **KOBIS_KEY를 찾을 수 없습니다.**

        Streamlit의 비밀 금고에 API 인증키를 등록해 주세요.

        `.streamlit/secrets.toml`을 사용할 경우:

        ```toml
        KOBIS_KEY = "발급받은_API_인증키"
        ```

        Streamlit Cloud에서는 앱의 **Settings → Secrets**에서
        같은 내용을 등록하면 됩니다.
        """
    )
    st.stop()


# ---------------------------------------------------------
# 5. API 오류가 발생한 경우 안내
# ---------------------------------------------------------
if not result["success"]:
    st.error(result["message"])
    st.stop()


df = result["data"]


# ---------------------------------------------------------
# 6. 1위 영화 강조
# ---------------------------------------------------------
first_movie = df.iloc[0]

st.markdown("### 🏆 박스오피스 1위")

st.markdown(
    f"## **{first_movie['movieNm']}**"
)

# 지표 카드 3개
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        "어제 관객수",
        f"{first_movie['audiCnt']:,}명"
    )

with col2:
    st.metric(
        "누적 관객수",
        f"{first_movie['audiAcc']:,}명"
    )

with col3:
    st.metric(
        "스크린수",
        f"{first_movie['scrnCnt']:,}개"
    )
# ---------------------------------------------------------
# 7. 관객수 상위 5편 막대그래프
# ---------------------------------------------------------
st.markdown("### 📊 관객수 상위 5편")

# 관객수 기준 내림차순 정렬
top5 = (
    df.sort_values(
        "audiCnt",
        ascending=False
    )
    .head(5)
    .copy()
)

# 현재 정렬된 영화 순서를 그대로 유지
movie_order = top5["movieNm"].tolist()

top5["movieNm"] = pd.Categorical(
    top5["movieNm"],
    categories=movie_order,
    ordered=True
)

chart_data = top5.set_index("movieNm")[["audiCnt"]]

st.bar_chart(
    chart_data,
    x_label="영화",
    y_label="관객수"
)
# ---------------------------------------------------------
# 8. 전체 박스오피스 표
# ---------------------------------------------------------
st.markdown("### 🎞️ 전체 박스오피스")

# 사용자에게 보여 줄 열 이름을 한글로 변경
display_df = df.rename(
    columns={
        "rank": "순위",
        "movieNm": "영화명",
        "openDt": "개봉일",
        "audiCnt": "관객수",
        "audiAcc": "누적관객",
        "scrnCnt": "스크린수"
    }
)

# 숫자를 천 단위 쉼표가 있는 문자열로 바꿔 보기 좋게 표시
table_df = display_df.copy()

table_df["관객수"] = table_df["관객수"].map(
    lambda x: f"{x:,}"
)

table_df["누적관객"] = table_df["누적관객"].map(
    lambda x: f"{x:,}"
)

table_df["스크린수"] = table_df["스크린수"].map(
    lambda x: f"{x:,}"
)

st.dataframe(
    table_df,
    use_container_width=True,
    hide_index=True
)


# ---------------------------------------------------------
# 9. 하단 안내
# ---------------------------------------------------------
st.caption(
    "자료 출처: 영화진흥위원회 영화관입장권통합전산망(KOBIS)"
)
