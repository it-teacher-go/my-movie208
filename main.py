import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


# ---------------------------------------------------------
# 1. 페이지 기본 설정
# ---------------------------------------------------------
st.set_page_config(
    page_title="일별 박스오피스",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 일별 박스오피스")
st.caption("영화진흥위원회 KOBIS 일별 박스오피스 데이터를 보여 줍니다.")


# ---------------------------------------------------------
# 2. 한국 시간 기준 날짜 설정
# ---------------------------------------------------------
KST = ZoneInfo("Asia/Seoul")

now_korea = datetime.now(KST)

today = now_korea.date()
yesterday = today - timedelta(days=1)


# ---------------------------------------------------------
# 날짜 선택
#
# 오늘 데이터는 아직 집계 전일 수 있으므로
# 최대 선택 가능 날짜는 어제로 제한합니다.
# ---------------------------------------------------------
selected_date = st.date_input(
    "📅 박스오피스 날짜를 선택하세요",
    value=yesterday,
    max_value=yesterday
)

# API에 전달할 날짜
# 예: 20260906
target_dt = selected_date.strftime("%Y%m%d")

# 화면 표시용 날짜
display_date = selected_date.strftime("%Y년 %m월 %d일")

st.subheader(f"📅 {display_date} 박스오피스")


# ---------------------------------------------------------
# 3. KOBIS API에서 데이터 가져오기
#
# 같은 날짜는 약 1시간 동안 캐시에 저장합니다.
# ---------------------------------------------------------
@st.cache_data(ttl=3600)
def load_boxoffice(target_date):

    # -----------------------------------------------------
    # Streamlit Secrets에서 API 인증키 가져오기
    # -----------------------------------------------------
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

        response = requests.get(
            url,
            params=params,
            timeout=10
        )

        response.raise_for_status()

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
    # 인증키 오류 등 확인
    # -----------------------------------------------------
    if "faultInfo" in data:

        fault = data["faultInfo"]

        message = fault.get(
            "message",
            "알 수 없는 API 오류입니다."
        )

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
    # 영화 목록 찾기
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


    # -----------------------------------------------------
    # 영화 목록이 비어 있는 경우
    # -----------------------------------------------------
    if not movies:

        return {
            "success": False,
            "message": "그날은 아직 집계 전입니다."
        }


    # -----------------------------------------------------
    # 필요한 열만 DataFrame으로 만들기
    # -----------------------------------------------------
    df = pd.DataFrame(movies)

    df = df[
        [
            "rank",
            "rankInten",
            "movieNm",
            "openDt",
            "audiCnt",
            "audiAcc",
            "scrnCnt"
        ]
    ].copy()


    # -----------------------------------------------------
    # 숫자형 변환
    # -----------------------------------------------------
    numeric_columns = [
        "rank",
        "rankInten",
        "audiCnt",
        "audiAcc",
        "scrnCnt"
    ]

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )


    df[numeric_columns] = (
        df[numeric_columns]
        .fillna(0)
        .astype(int)
    )


    # -----------------------------------------------------
    # 순위 기준 정렬
    # -----------------------------------------------------
    df = (
        df.sort_values(
            "rank",
            ascending=True
        )
        .reset_index(drop=True)
    )


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
# 5. API 오류가 발생한 경우
# ---------------------------------------------------------
if not result["success"]:

    st.info(result["message"])

    st.stop()


df = result["data"]


# ---------------------------------------------------------
# 6. 박스오피스 1위 강조
# ---------------------------------------------------------
first_movie = df.iloc[0]

# 누적관객 100만 초과 시 트로피 표시
first_movie_name = first_movie["movieNm"]

if first_movie["audiAcc"] > 1_000_000:
    first_movie_name += " 🏆"


st.markdown("### 🥇 박스오피스 1위")

st.markdown(
    f"## **{first_movie_name}**"
)


# ---------------------------------------------------------
# 지표 카드 3개
# ---------------------------------------------------------
col1, col2, col3 = st.columns(3)


with col1:

    st.metric(
        "당일 관객수",
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


# ---------------------------------------------------------
# 현재 관객수 순서를 그대로 유지
# ---------------------------------------------------------
movie_order = top5["movieNm"].tolist()

top5["movieNm"] = pd.Categorical(
    top5["movieNm"],
    categories=movie_order,
    ordered=True
)


chart_data = (
    top5
    .set_index("movieNm")[["audiCnt"]]
)


st.bar_chart(
    chart_data,
    x_label="영화",
    y_label="관객수"
)


# ---------------------------------------------------------
# 8. 전체 박스오피스 표
# ---------------------------------------------------------
st.markdown("### 🎞️ 전체 박스오피스")


display_df = df.copy()


# ---------------------------------------------------------
# 순위 변동 표시 만들기
#
# rankInten > 0 : 전날보다 순위 상승
# rankInten < 0 : 전날보다 순위 하락
# rankInten = 0 : 변동 없음
# ---------------------------------------------------------
def rank_change_text(value):

    if value > 0:
        return f"🔺 {value}"

    elif value < 0:
        return f"🔻 {abs(value)}"

    else:
        return "ㅡ"


display_df["순위변동"] = (
    display_df["rankInten"]
    .apply(rank_change_text)
)


# ---------------------------------------------------------
# 누적관객 100만 명 초과 시 영화명에 트로피 붙이기
# ---------------------------------------------------------
display_df["movieNm"] = display_df.apply(
    lambda row: (
        f"{row['movieNm']} 🏆"
        if row["audiAcc"] > 1_000_000
        else row["movieNm"]
    ),
    axis=1
)


# ---------------------------------------------------------
# 사용자에게 보여 줄 열 이름 변경
# ---------------------------------------------------------
display_df = display_df.rename(
    columns={
        "rank": "순위",
        "movieNm": "영화명",
        "openDt": "개봉일",
        "audiCnt": "관객수",
        "audiAcc": "누적관객",
        "scrnCnt": "스크린수"
    }
)


# ---------------------------------------------------------
# 보여 줄 열 순서 지정
# ---------------------------------------------------------
display_df = display_df[
    [
        "순위",
        "순위변동",
        "영화명",
        "개봉일",
        "관객수",
        "누적관객",
        "스크린수"
    ]
].copy()


# ---------------------------------------------------------
# 숫자형 유지
#
# 이렇게 해야 표에서 클릭 정렬할 때
# 문자순이 아니라 숫자 크기순으로 정렬됩니다.
# ---------------------------------------------------------
numeric_columns = [
    "순위",
    "관객수",
    "누적관객",
    "스크린수"
]


for column in numeric_columns:

    display_df[column] = (
        pd.to_numeric(
            display_df[column],
            errors="coerce"
        )
        .fillna(0)
        .astype(int)
    )


# ---------------------------------------------------------
# 표 출력
# ---------------------------------------------------------
st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    column_config={

        "순위": st.column_config.NumberColumn(
            "순위",
            format="%d"
        ),

        "순위변동": st.column_config.TextColumn(
            "전일 대비"
        ),

        "영화명": st.column_config.TextColumn(
            "영화명"
        ),

        "개봉일": st.column_config.TextColumn(
            "개봉일"
        ),

        "관객수": st.column_config.NumberColumn(
            "관객수",
            format="%,d"
        ),

        "누적관객": st.column_config.NumberColumn(
            "누적관객",
            format="%,d"
        ),

        "스크린수": st.column_config.NumberColumn(
            "스크린수",
            format="%,d"
        )
    }
)


# ---------------------------------------------------------
# 9. 안내
# ---------------------------------------------------------
st.caption(
    "🔺 전날보다 순위 상승 · 🔻 전날보다 순위 하락 · 🏆 누적관객 100만 명 초과"
)

st.caption(
    "자료 출처: 영화진흥위원회 영화관입장권통합전산망(KOBIS)"
)
