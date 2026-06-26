import os
import re
import json
import difflib
from openai import OpenAI
from app.core.config import GEMINI_API_KEY, GEMINI_BASE_URL, MODEL_NAME, BASE_DIR
from app.services.retriever import HybridRulesRetriever
from app.services.normalizer import enterprise_persian_normalizer

client = OpenAI(
    base_url=GEMINI_BASE_URL,
    api_key=GEMINI_API_KEY
)

retriever_instance = HybridRulesRetriever()

DATA_DIR = os.path.join(BASE_DIR, "data")

with open(os.path.join(DATA_DIR, 'Buildings.json'), 'r', encoding='utf-8') as f:
    buildings_db = json.load(f)
with open(os.path.join(DATA_DIR, 'Rooms.json'), 'r', encoding='utf-8') as f:
    rooms_db = json.load(f)
with open(os.path.join(DATA_DIR, 'Professors.json'), 'r', encoding='utf-8') as f:
    professors_db = json.load(f)
with open(os.path.join(DATA_DIR, 'Org_chart.json'), 'r', encoding='utf-8') as f:
    org_chart_db = json.load(f)
with open(os.path.join(DATA_DIR, 'Courses.json'), 'r', encoding='utf-8') as f:
    courses_db = json.load(f)
with open(os.path.join(DATA_DIR, 'Study_plan.json'), 'r', encoding='utf-8') as f:
    study_plan_db = json.load(f)
with open(os.path.join(DATA_DIR, 'Staff.json'), 'r', encoding='utf-8') as f:
    staff_db = json.load(f)
with open(os.path.join(DATA_DIR, 'Links.json'), 'r', encoding='utf-8') as f:
    links_db = json.load(f)

links_list = links_db.get("links", []) if isinstance(links_db, dict) else links_db
LINKS_MAP = {str(link.get('id')): link.get('url', '#') for link in links_list}


def compress_name_for_search(normalized_name: str) -> str:
    """
    فاصله‌ها را حذف می‌کند تا نام و نام‌خانوادگی به هم بچسبند.
    این کار دقت کتابخانه difflib را برای نام‌هایی که با فاصله/نیم‌فاصله متفاوت تایپ شده‌اند بالا می‌برد.
    نکته: ورودی این تابع باید قبلاً توسط normalize_text استاندارد شده باشد.
    """
    if not normalized_name:
        return ""
    
    compressed_name = re.sub(r'\s+', '', normalized_name)
    compressed_name = compressed_name.replace('\u200c', '') 
    
    return compressed_name


def normalize_text(text: str) -> str:
    """استانداردسازی پیشرفته متن فارسی برای جستجوی دقیق‌تر"""
    if not text:
        return ""
    
    text = str(text).lower()
    
    num_mapping = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
    text = text.translate(num_mapping)
    
    char_mapping = str.maketrans('يكآأإؤئة', 'یکاااويه')
    text = text.translate(char_mapping)
    
    text = re.sub(r'[\u064B-\u065F]', '', text)
    
    text = text.replace('\u200c', ' ')
    
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def _find_best_course_match(course_name: str, courses_list: list) -> dict | None:
    """تابع کمکی داخلی برای جستجوی هوشمند درس در دیتابیس"""
    clean_query = normalize_text(course_name)
    query_no_space = compress_name_for_search(clean_query)

    best_course = None
    best_score = 0

    for course in courses_list:
        score = 0
        name = normalize_text(course.get("name", ""))
        name_no_space = compress_name_for_search(name)

        if query_no_space == name_no_space:
            score += 100
        elif query_no_space in name_no_space or name_no_space in query_no_space:
            score += 50

        similarity = difflib.SequenceMatcher(None, query_no_space, name_no_space).ratio()
        if similarity > 0.7:
            score += int(similarity * 30)

        for word in clean_query.split():
            if len(word) > 2 and word in name:
                score += 10

        if score > best_score:
            best_score = score
            best_course = course

    if best_score < 30:
        return None
        
    return best_course



def get_professor_info(professor_name: str) -> str:
    """اطلاعات استاد به همراه آدرس دقیق دفترش را برمی‌گرداند"""
    
    base_normalized = normalize_text(professor_name)

    clean_name = re.sub(r'\b(دکتر|استاد|مهندس|پروفسور|پرفسور|آقای|آقا|خانم)\b', '', base_normalized).strip()
    
    fully_normalized_query = compress_name_for_search(clean_name)

    search_keywords = [kw for kw in clean_name.split() if len(kw) > 2]

    professors_list = professors_db.get("professors", []) if isinstance(professors_db, dict) else professors_db
    
    best_match = None
    highest_score = 0

    for prof in professors_list:
        prof_full_name = prof.get("name", "")
        cleaned_name = re.sub(r'^(دکتر|مهندس)\s+', '', prof_full_name).strip()
        base_normalized_prof_name = normalize_text(cleaned_name)
        normalized_prof_name = compress_name_for_search(base_normalized_prof_name)
        
        score = 0
        
        similarity_ratio = difflib.SequenceMatcher(None, fully_normalized_query, normalized_prof_name).ratio()
        score += (similarity_ratio * 10)
        
        for keyword in search_keywords:
            if keyword in normalized_prof_name:
                score += 2
                
        if fully_normalized_query and fully_normalized_query in normalized_prof_name:
            score += 5 

        if score > highest_score:
            highest_score = score
            best_match = prof

    if not best_match or highest_score < 4.5:
        error_msg = {
            "error": "استادی با این نام در دانشکده پیدا نشد.",
            "instruction": "لطفاً عیناً همین پیام خطا را با لحنی محترمانه به کاربر اعلام کن و از خودت هیچ لینکی نساز."
        }
        return json.dumps(error_msg, ensure_ascii=False)

    found_prof = best_match

    response_data = {
        "نام": found_prof.get("name"),
        "مرتبه علمی": found_prof.get("title"),
        "عضو دانشکده": found_prof.get("department"),
        "ایمیل": found_prof.get("email"),
        "حوزه‌های پژوهشی": found_prof.get("research_interests"),
        "صفحات مرتبط": found_prof.get("profile_pages"),
        "لینک صفحه google scholar": found_prof.get("google_scholar_url"),
    }

    room_ids = found_prof.get("office_room_id", [])
    if room_ids and len(room_ids) > 0:
        target_room_id = room_ids[0] 
        rooms_list = rooms_db.get("rooms", []) if isinstance(rooms_db, dict) else rooms_db
        
        for room in rooms_list:
            if room.get("id") == target_room_id:
                response_data["نام_دفتر"] = room.get("name")
                response_data["طبقه"] = room.get("floor")
                response_data["راهنمای مسیر دفتر در ساختمان"] = room.get("path_description")
                
                
                building_id = room.get("building_id")
                if building_id:
                    buildings_list = buildings_db.get("buildings", []) if isinstance(buildings_db, dict) else buildings_db
                    for bldg in buildings_list:
                        if bldg.get("id") == building_id:
                            response_data["نام رسمی ساختمان"] = bldg.get("official_name")
                            response_data["نام دیگر ساختمان"] = bldg.get("common_names")

                            loc = bldg.get("location")
                            if loc and loc.get("latitude") and loc.get("longitude"):
                                lat = round(loc.get("latitude"), 6)
                                lng = round(loc.get("longitude"), 6)
                                response_data["لینک مسیریابی"] = {
                                    "نشان": f"MASK_MAP_NESHAN_{lat}_{lng}",
                                    "بلد": f"MASK_MAP_BALAD_{lat}_{lng}"
                                }
                            break
                break

    return json.dumps(response_data, ensure_ascii=False)



def search_facility_or_room(target_location: str, building_name: str = None, floor_number: int | str | None = None) -> str:
    """جستجوی مکان‌ها بر اساس پارامترهای استخراج شده توسط هوش مصنوعی"""

    rooms_list = rooms_db.get("rooms", []) if isinstance(rooms_db, dict) else rooms_db
    buildings_list = buildings_db.get("buildings", []) if isinstance(buildings_db, dict) else buildings_db

    target_floor = None
    if floor_number is not None:
        try:
            target_floor = int(floor_number)
        except (ValueError, TypeError):
            target_floor = None

    clean_target = normalize_text(target_location)
    
    building_filter = None
    if building_name:
        clean_building = normalize_text(building_name)
        best_building_score = 0
        for building in buildings_list:
            score = 0
            official_name = normalize_text(building.get("official_name", ""))
            common_names = normalize_text(" ".join(building.get("common_names", [])))
            
            for word in clean_building.split():
                if len(word) > 2 and (word in official_name or word in common_names):
                    score += 1
                    
            if score > best_building_score:
                best_building_score = score
                building_filter = building.get("id")

    candidates = []
    
    for room in rooms_list:
        if building_filter and room.get("building_id") != building_filter:
            continue
            
        if target_floor is not None and room.get("floor") is not None:
            if room.get("floor") != target_floor:
                continue

        score = 0
        room_name = normalize_text(room.get("name", ""))
        tags_list = room.get("tags") or []
        tags = normalize_text(" ".join(tags_list))
        description_text = normalize_text(str(room.get("description", "")) + " " + str(room.get("usage_description", "")))

        if clean_target and clean_target in tags:
            score += 50
        if clean_target and clean_target in room_name:
            score += 30

        for word in clean_target.split():
            if len(word) > 2:
                if word in tags:
                    score += 20
                elif word in room_name:
                    score += 10
                elif word in description_text:
                    score += 2

        if score > 0:
            candidates.append({"room": room, "score": score})

    if not candidates:
        error_msg = {
            "error": "مکانی با این مشخصات پیدا نشد.",
            "instruction": "لطفاً عیناً همین پیام خطا را با لحنی محترمانه به کاربر اعلام کن و از خودت هیچ لینکی نساز."
        }
        return json.dumps(error_msg, ensure_ascii=False)

    top_score = max(c["score"] for c in candidates)
    threshold = top_score - 10 if (building_filter or target_floor is not None) else top_score - 5
    top_candidates = [c for c in candidates if c["score"] >= threshold]

    def build_room_response(room):
        data = {
            "نام مکان": room.get("name"),
            "نوع مکان": room.get("type"),
            "طبقه": room.get("floor"),
            "راهنمای مسیر مکان خواسته شده": room.get("path_description"),
            "توضیحات": room.get("description"),
            "اطلاعات تماس": room.get("contacts")
        }

        b_id = room.get("building_id")
        bldg = None
        if b_id:
            bldg = next((b for b in buildings_list if b.get("id") == b_id), None)
            if bldg:
                data["نام ساختمان"] = bldg.get("official_name")
        
        loc = room.get("location")
        if not loc and bldg:
            loc = bldg.get("location")
            
        if loc and loc.get("latitude") and loc.get("longitude"):
            lat = round(loc.get("latitude"), 6)
            lng = round(loc.get("longitude"), 6)
            data["لینک مسیریابی"] = {
                "نشان": f"MASK_MAP_NESHAN_{lat}_{lng}",
                "بلد": f"MASK_MAP_BALAD_{lat}_{lng}"
            }

        return {k: v for k, v in data.items() if v}

    if len(top_candidates) > 1:
        results = [build_room_response(c["room"]) for c in top_candidates]
        return json.dumps({"نتایج متعدد": results}, ensure_ascii=False)

    return json.dumps(build_room_response(top_candidates[0]["room"]), ensure_ascii=False)



def get_role_holder(role_title: str) -> str:
    """پیدا کردن مسئول یک سمت سازمانی و اطلاعات تماس او"""

    clean_query = normalize_text(role_title)

    org_list = org_chart_db.get("roles", []) if isinstance(org_chart_db, dict) else org_chart_db
    professors_list = professors_db.get("professors", []) if isinstance(professors_db, dict) else professors_db
    rooms_list = rooms_db.get("rooms", []) if isinstance(rooms_db, dict) else rooms_db
    buildings_list = buildings_db.get("buildings", []) if isinstance(buildings_db, dict) else buildings_db

    best_role = None
    best_score = 0

    for role in org_list:
        score = 0
        title = normalize_text(role.get("role_title", ""))

        if clean_query == title:
            score += 50
        elif clean_query in title or title in clean_query:
            score += 20

        for word in clean_query.split():
            if len(word) > 2 and word in title:
                score += 10

        if score > best_score:
            best_score = score
            best_role = role

    if not best_role or best_score == 0:
        error_msg = {
            "error": "سمتی با این عنوان در چارت سازمانی پیدا نشد.",
            "instruction": "لطفاً عیناً همین پیام خطا را با لحنی محترمانه به کاربر اعلام کن و از خودت هیچ لینکی نساز."
        }
        return json.dumps(error_msg, ensure_ascii=False)

    response_data = {
        "سمت": best_role.get("role_title")
    }

    contacts = best_role.get("contacts")
    if contacts:
        for contact in contacts:
            label = contact.get("label")
            value = contact.get("value")
            if label and value:
                response_data[label] = value

    professor_id = best_role.get("professor_id")
    if professor_id:
        professor_data = next((p for p in professors_list if p.get("id") == professor_id), None)
        if professor_data:
            response_data["صاحب منصب فعلی"] = professor_data.get("name")
            response_data["مرتبه علمی"] = professor_data.get("title")
            response_data["ایمیل"] = professor_data.get("email")

    office_room_id = best_role.get("office_room_id")
    
    if office_room_id:
        room = next((r for r in rooms_list if r.get("id") == office_room_id), None)
        
        if room:
            b_id = room.get("building_id")
            bldg = None
            building_name = None
            if b_id:
                bldg = next((b for b in buildings_list if b.get("id") == b_id), None)
                if bldg:
                    building_name = bldg.get("official_name")

            response_data["دفتر محل استقرار"] = {
                "نام دفتر": room.get("name"),
                "طبقه": room.get("floor"),
                "مسیر دسترسی": room.get("path_description"),
                "نام ساختمان": building_name
            }

    return json.dumps(response_data, ensure_ascii=False)



def get_building_info(building_name: str) -> str:
    """اطلاعات کلی یک ساختمان را برمی‌گرداند"""

    clean_query = normalize_text(building_name)

    buildings_list = buildings_db.get("buildings", []) if isinstance(buildings_db, dict) else buildings_db

    best_building = None
    best_score = 0

    for building in buildings_list:
        score = 0
        official_name = normalize_text(building.get("official_name", ""))
        
        normalized_common_names_list = [normalize_text(name) for name in building.get("common_names", [])]
        
        common_names_string = " ".join(normalized_common_names_list)

        if clean_query == official_name or clean_query in normalized_common_names_list:
            score += 50

        for word in clean_query.split():
            if len(word) > 2:
                if word in official_name or word in common_names_string:
                    score += 15

        if score > best_score:
            best_score = score
            best_building = building

    if not best_building or best_score == 0:
        error_msg = {
            "error": "ساختمانی با این نام پیدا نشد.",
            "instruction": "لطفاً عیناً همین پیام خطا را با لحنی محترمانه به کاربر اعلام کن و از خودت هیچ لینکی نساز."
        }
        return json.dumps(error_msg, ensure_ascii=False)

    response_data = {
        "نام رسمی": best_building.get("official_name"),
        "نام های دیگر": best_building.get("common_names"),
        "نوع ساختمان": best_building.get("type"),
        "تعداد طبقات": best_building.get("floors"),
        "وضعیت": best_building.get("status"),
        "توضیحات": best_building.get("description"),
    }
    
    loc = best_building.get("location")
    if loc and loc.get("latitude") and loc.get("longitude"):
        lat = round(loc.get("latitude"), 6)
        lng = round(loc.get("longitude"), 6)
        response_data["لینک مسیریابی"] = {
            "نشان": f"MASK_MAP_NESHAN_{lat}_{lng}",
            "بلد": f"MASK_MAP_BALAD_{lat}_{lng}"
        }

    return json.dumps(response_data, ensure_ascii=False)



def get_course_details(course_name: str) -> str:
    """اطلاعات یک درس خاص"""

    if not course_name or not course_name.strip():
        error_msg = {
            "error": "نام درس وارد نشده است.",
            "instruction": "از کاربر بخواه نام درس را بگوید."
        }
        return json.dumps(error_msg, ensure_ascii=False)


    courses_list = courses_db.get("courses", []) if isinstance(courses_db, dict) else courses_db

    courses_map = {c["id"]: c["name"] for c in courses_list}

    best_course = _find_best_course_match(course_name, courses_list)

    if not best_course:
        error_msg = {
            "error": f"درسی با نام '{course_name}' پیدا نشد.",
            "instruction": "لطفاً عیناً همین پیام خطا را با لحنی محترمانه به کاربر اعلام کن و از خودت هیچ لینکی نساز."
        }
        return json.dumps(error_msg, ensure_ascii=False)


    prerequisites = [
        courses_map.get(cid, cid)
        for cid in best_course.get("prerequisites", [])
    ]

    corequisites = [
        courses_map.get(cid, cid)
        for cid in best_course.get("corequisites", [])
    ]

    response_data = {
        "نام درس": best_course.get("name"),
        "تعداد واحد": best_course.get("units"),
        "دسته‌بندی": best_course.get("category"),
        "نوع": best_course.get("type"),
        "پیش‌نیازها": prerequisites if prerequisites else "ندارد",
        "هم‌نیازها": corequisites if corequisites else "ندارد",
    }

    return json.dumps(response_data, ensure_ascii=False)



def get_study_plan(semester_number: int | str | None = None, course_name: str = None) -> str:
    """مشاوره برنامه‌ریزی تحصیلی: دروس پیشنهادی یک ترم یا ترم پیشنهادی یک درس"""
    
    courses_list = courses_db.get("courses", []) if isinstance(courses_db, dict) else courses_db
    plans_list = study_plan_db.get("plans", []) if isinstance(study_plan_db, dict) else study_plan_db

    target_semester = None
    if semester_number is not None:
        try:
            target_semester = int(semester_number)
        except (ValueError, TypeError):
            target_semester = None
    
    courses_map = {c["id"]: c["name"] for c in courses_list}


    if course_name:
        best_course = _find_best_course_match(course_name, courses_list)

        if not best_course:
            error_msg = {
                "error": f"درسی با نام '{course_name}' در دیتابیس دروس پیدا نشد.",
                "instruction": "لطفاً عیناً همین پیام خطا را با لحنی محترمانه به کاربر اعلام کن و از خودت هیچ لینکی نساز."
            }
            return json.dumps(error_msg, ensure_ascii=False)
        
        best_course_id = best_course.get("id")
        best_course_name = best_course.get("name")

        found_in_plans = []
        for plan in plans_list:
            plan_name = plan.get("name", "چارت نامشخص")
            for semester in plan.get("semesters", []):
                for item in semester.get("items", []):
                    if item.get("course_id") == best_course_id:
                        found_in_plans.append({
                            "نام چارت": plan_name,
                            "ترم پیشنهادی": semester.get("semester_number")
                        })
                        break

        if found_in_plans:
            return json.dumps({
                "نام درس": best_course_name,
                "پیشنهادات چارت": found_in_plans,
                "پیام سیستم": f"این درس در {len(found_in_plans)} چارت مختلف پیدا شد."
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "نام درس": best_course_name,
                "پیام سیستم": "این درس در لیست دروس وجود دارد اما در هیچکدام از چارت‌های پیشنهادی ثبت نشده است."
            }, ensure_ascii=False)

    elif target_semester is not None:
        semester_info = []
        
        for plan in plans_list:
            plan_name = plan.get("name", "چارت نامشخص")
            for semester in plan.get("semesters", []):
                if semester.get("semester_number") == target_semester:
                    courses_in_this_semester = []
                    
                    for item in semester.get("items", []):
                        if item.get("type") == "course":
                            c_name = courses_map.get(item.get("course_id"), item.get("course_id"))
                            courses_in_this_semester.append(c_name)
                        elif item.get("type") == "slot":
                            slot_name = f"{item.get('name')} ({item.get('units')} واحد)"
                            courses_in_this_semester.append(slot_name)
                            
                    semester_info.append({
                        "نام چارت": plan_name,
                        "مجموع واحد پیشنهادی": semester.get("recommended_units"),
                        "دروس": courses_in_this_semester
                    })
                    break
        
        if semester_info:
            return json.dumps({
                "شماره ترم": target_semester,
                "اطلاعات چارت‌ها": semester_info
            }, ensure_ascii=False)
        else:
            error_msg = {
                "error": f"اطلاعاتی برای ترم {target_semester} در چارت‌ها یافت نشد.",
                "instruction": "لطفاً عیناً همین پیام خطا را با لحنی محترمانه به کاربر اعلام کن و از خودت هیچ لینکی نساز."
            }
            return json.dumps(error_msg, ensure_ascii=False)
        
    error_msg = {
        "error": "لطفا نام درس یا شماره ترم را مشخص کنید.",
        "instruction": "لطفاً عیناً همین پیام خطا را با لحنی محترمانه به کاربر اعلام کن و از خودت هیچ لینکی نساز."
    }
    return json.dumps(error_msg, ensure_ascii=False)
    


def get_staff_info(query: str) -> str:
    """اطلاعات کارمند/مسئول اداری به همراه وظایف و آدرس دقیق دفترش را برمی‌گرداند"""
    
    clean_query = normalize_text(query)
    clean_query = re.sub(r'\b(استاد|مهندس|آقای|آقا|خانم)\b', '', clean_query).strip()
    search_keywords = clean_query.split()

    staff_list = staff_db.get("staff", []) if isinstance(staff_db, dict) else staff_db
    
    scored_matches = []

    for staff in staff_list:
        staff_name = normalize_text(staff.get("name", ""))
        staff_role = normalize_text(staff.get("role", ""))
        staff_tags = [normalize_text(tag) for tag in (staff.get("tags") or []) if tag]
        
        score = 0
        
        for keyword in search_keywords:
            if len(keyword) > 2:
                if keyword in staff_name: score += 1
                if keyword in staff_role: score += 1
                if any(keyword in tag for tag in staff_tags): score += 1
                
        if clean_query in staff_name: score += 5 
        if clean_query in staff_role: score += 5
        if any(clean_query == tag for tag in staff_tags): score += 5

        if score > 0:
            scored_matches.append({
                "score": score,
                "staff": staff
            })

    if not scored_matches:
        error_msg = {
            "error": "کارمند یا مسئولی با این مشخصات در دانشکده پیدا نشد.",
            "instruction": "لطفاً عیناً همین پیام خطا را با لحنی محترمانه به کاربر اعلام کن و از خودت هیچ لینکی نساز."
        }
        return json.dumps(error_msg, ensure_ascii=False)

    scored_matches.sort(key=lambda x: x["score"], reverse=True)
    
    top_matches = [item["staff"] for item in scored_matches[:3]]

    rooms_list = rooms_db.get("rooms", []) if isinstance(rooms_db, dict) else rooms_db
    buildings_list = buildings_db.get("buildings", []) if isinstance(buildings_db, dict) else buildings_db

    rooms_map = {room.get("id"): room for room in rooms_list}
    buildings_map = {bldg.get("id"): bldg for bldg in buildings_list}

    results = []

    for found_staff in top_matches:
        response_data = {
            "نام": found_staff.get("name"),
            "نقش یا سمت": found_staff.get("role"),
            "مقطع فعالیت": found_staff.get("program"),
            "ایمیل": found_staff.get("email"),
            "تلفن تماس": found_staff.get("phone", []),
            "محل میز یا باجه": found_staff.get("desk_location"),
            "حوزه مسئولیت و وظایف": found_staff.get("tags", [])
        }

        target_room_id = found_staff.get("room_id") 
        if target_room_id and target_room_id in rooms_map:
            room = rooms_map[target_room_id]
            response_data.update({
                "نام دفتر یا اداره": room.get("name"),
                "طبقه": room.get("floor"),
                "راهنمای مسیر در ساختمان": room.get("path_description"),
                "توضیحات": room.get("description"),
                "توضیحات استفاده": room.get("usage_description")
            })

            building_id = room.get("building_id")
            if building_id and building_id in buildings_map:
                bldg = buildings_map[building_id]
                response_data.update({
                    "نام رسمی ساختمان": bldg.get("official_name"),
                    "نام دیگر ساختمان": bldg.get("common_names"),
                })

                loc = bldg.get("location")
                if loc and loc.get("latitude") and loc.get("longitude"):
                    lat = round(loc.get("latitude"), 6)
                    lng = round(loc.get("longitude"), 6)
                    response_data["لینک مسیریابی"] = {
                        "نشان": f"MASK_MAP_NESHAN_{lat}_{lng}",
                        "بلد": f"MASK_MAP_BALAD_{lat}_{lng}"
                    }
                    
        results.append(response_data)

    final_output = results[0] if len(results) == 1 else results
    return json.dumps(final_output, ensure_ascii=False)



def get_university_link(query: str, category: str = None):
    """
    جستجوی هوشمند لینک‌ها با تکنیک Stateless URL Masking (مبتنی بر ID)
    """
    links_list = links_db.get("links", []) if isinstance(links_db, dict) else links_db

    normalized_query = normalize_text(query)
    stop_words = {"سامانه", "سایت", "لینک", "پورتال", "دانشگاه", "ورود", "به", "برای", "سیستم", "وبسایت", "وب سایت"}
    query_words = [word for word in normalized_query.split() if word not in stop_words]
    
    if not query_words:
        query_words = [normalized_query]

    scored_results = []

    for link in links_list:
        link_category = link.get("category", "")
        if category and category.lower() != link_category.lower():
            continue

        score = 0
        link_title = normalize_text(link.get("title", ""))
        link_desc = normalize_text(link.get("description", ""))
        link_keywords = [normalize_text(k) for k in link.get("keywords", [])]

        if normalized_query in link_title:
            score += 50
            
        for word in query_words:
            if any(word in kw for kw in link_keywords):
                score += 20
            if word in link_title:
                score += 10
            if word in link_desc:
                score += 5

        if score > 0:
            scored_results.append({
                "score": score,
                "data": {
                    "عنوان": link.get("title"),
                    "url": f"MASK_{link.get('id')}", 
                    "توضیحات": link.get("description")
                }
            })

    if not scored_results:
        error_msg = {
            "error": f"هیچ لینک یا سامانه‌ای مرتبط با جستجوی '{query}' یافت نشد.",
            "instruction": "لطفاً عیناً همین پیام خطا را با لحنی محترمانه به کاربر اعلام کن و از خودت هیچ لینکی نساز."
        }
        return json.dumps(error_msg, ensure_ascii=False)

    scored_results.sort(key=lambda x: x["score"], reverse=True)
    top_3_results = [item["data"] for item in scored_results[:3]]

    return json.dumps({
        "message": f"تعداد {len(top_3_results)} سامانه یافت شد  اما تو به عنوان یک ناظر هوشمند، نتایج را بررسی کن. اگر ابزار سامانه‌ای را برگرداند که ذاتاً ارتباطی با مفهوم درخواست کاربر ندارد (مثلاً کاربر ‘گواهی اشتغال’ می‌خواهد اما ابزار ‘سایت تحصیلات تکمیلی’ را برگردانده است)، آن مورد نامربوط را از پاسخ نهایی و جدول خود به صورت سایلنت حذف کن و فقط سامانه‌هایی که دقیقاً پاسخگوی نیاز کاربر هستند را در یک جدول مارک‌داون نشان بده و مقادیر url را دقیقاً و عیناً در ستون لینک قرار بده.",
        "results": top_3_results
    }, ensure_ascii=False)



def get_educational_rules(corrected_query: str, search_tasks: list) -> str:
    """
    جستجو در شیوه نامه اجرایی آموزش با قابلیت تجزیه کوئری و کلمات کلیدی اختصاصی.
    """
    print(f"\n[RAG] 1. Corrected Query: {corrected_query}")
    
    if not search_tasks:
        search_tasks = [{"sub_query": corrected_query, "expanded_keywords": ""}]
        
    unique_docs = {}
    
    top_k_per_query = max(10, 12 // len(search_tasks))
    
    for idx, task in enumerate(search_tasks):
        sub_query = task.get("sub_query", "")
        expanded_keywords = task.get("expanded_keywords", "")
        
        normalized_semantic = enterprise_persian_normalizer(sub_query)
        normalized_keywords = enterprise_persian_normalizer(expanded_keywords)
        
        print(f"[RAG] 2. Task {idx+1} Semantic: {normalized_semantic} | Keywords: {normalized_keywords}")
        
        retrieved_docs = retriever_instance.search(
            semantic_query=normalized_semantic, 
            keyword_query=normalized_keywords,
            top_k=top_k_per_query
        )
        
        for doc in retrieved_docs:
            doc_id = doc['id']
            if doc_id not in unique_docs or doc['score'] > unique_docs[doc_id]['score']:
                unique_docs[doc_id] = doc

    final_sorted_docs = sorted(unique_docs.values(), key=lambda x: x['score'], reverse=True)
    
    final_sorted_docs = final_sorted_docs[:12]

    if not final_sorted_docs:
        error_msg = {
            "error": "در آیین‌نامه‌ها و قوانین آموزشی موردی در این باره یافت نشد.",
            "instruction": "لطفاً عیناً همین پیام خطا را با لحنی محترمانه به کاربر اعلام کن و از خودت هیچ لینکی نساز."
        }
        return json.dumps(error_msg, ensure_ascii=False)

    context_text = (
        "اطلاعات زیر از جستجو در بخش‌های مختلف آیین‌نامه‌ها و قوانین آموزشی به دست آمده است. "
        "ابتدا با دقت بررسی کن که آیا این متن‌ها شامل پاسخی برای سوال کاربر هستند یا خیر:\n"
        "۱. اگر متن‌ها مرتبط بودند: فقط بر اساس همین اطلاعات پاسخ بده و حتماً شماره ماده و تبصره را به دقت ذکر کن. دقت کن که اگر در متن‌ها، استثنائات قانونی یا تبصره‌های خاصی (مانند شرایط خاص برای نمرات، سنوات یا مرخصی‌ها) ذکر شده است، حتماً آن‌ها را در پاسخ خود بگنجان تا دانشجو دچار اشتباه نشود.\n"
        "۲. اگر سوال مقایسه‌ای یا چند بخشی است: اطلاعات مربوط به هر بخش را از متن‌های مختلف زیر استخراج و ترکیب کن.\n"
        "۳. اگر برخی از متن‌ها بی‌ربط بودند: آن‌ها را کاملاً نادیده بگیر و فقط از بخش‌های مرتبط استفاده کن.\n"
        "۴. اگر هیچ‌کدام از متن‌های زیر ارتباطی به سوال کاربر نداشتند: به هیچ وجه اطلاعاتی از خودت نساز و صراحتاً بگو «با توجه به آیین‌نامه‌های موجود، پاسخ دقیقی برای این سوال یافت نشد.»\n\n"
        "متن‌های یافت شده:\n\n"
    )

    
    for i, doc in enumerate(final_sorted_docs):
        title = doc.get('title', 'بدون عنوان')
        text = doc.get('text', '')
        context_text += f"--- منبع {i+1} ({title}) ---\n{text}\n\n"
    

    return context_text



tools = [
    {
        "type": "function",
        "function": {
            "name": "get_professor_info",
            "description": "برای پیدا کردن اطلاعات، رزومه یا اتاق اساتید هیئت علمی (با پیشوند دکتر یا استاد) استفاده می‌شود. نکته: اگر کاربر به جای نام استاد، فقط «سمت» او را پرسید (مثل مدیر گروه یا رئیس دانشکده)، به جای این ابزار، مستقیماً از get_role_holder استفاده کن.",
            "parameters": {
                "type": "object",
                "properties": {
                    "professor_name": {
                        "type": "string",
                        "description": "نام یا نام خانوادگی استاد (بدون کلمات دکتر یا استاد).",
                    }
                },
                "required": ["professor_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_facility_or_room",
            "description": "فقط برای پیدا کردن مکان‌های فیزیکیِ «داخل» ساختمان‌ها استفاده می‌شود: ۱. کلاس‌ها و آزمایشگاه‌ها. ۲. امکانات رفاهی (کافه، نمازخانه، سرویس بهداشتی، آبخوری). ۳. مکان دفاتر و سایت‌ها.\nنکته مسیردهی: اگر کاربر اطلاعات یا آدرسِ «کل یک ساختمان» را خواست، این ابزار را رها کن و مستقیماً ابزار get_building_info را فراخوانی کن.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_location": {
                        "type": "string",
                        "description": "نام اصلی مکان یا امکانات (مثلاً: کلاس 201، دفتر امور دانشجویی، سایت کامپیوتر، کافه). دقت کن که نام ساختمان را در این فیلد نیاوری و کلمات اضافه مثل 'کجاست' را حذف کنی."
                    },
                    "building_name": {
                        "type": "string",
                        "description": "نام اصلی ساختمان در صورت ذکر شدن (مثلاً: اداری کامپیوتر، قدیمی اساتید، ساختمان اصلی، فضای باز). کلمات پیشوند مثل 'ساختمان' را حذف کن. اگر کاربر فقط از کلمات عمومی مثل «دانشکده» یا «اینجا» استفاده کرد، این فیلد را خالی بگذار."
                    },
                    "floor_number": {
                        "type": "integer",
                        "description": "شماره طبقه در صورت ذکر شدن (مثلا همکف = 0، اول = 1، دوم = 2). اگر ذکر نشده بود خالی بگذار."
                    }
                },
                "required": ["target_location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_role_holder",
            "description": "استفاده اصلی برای پیدا کردن نام و اطلاعات تماس اشخاصی که دارای «سمت‌های مدیریتی و ارشد» هستند. هر زمان کلماتی مانند «مدیر»، «رئیس»، «معاون» یا «مدیر گروه» در سوال کاربر بود، حتماً این ابزار را فراخوانی کن. مثال‌ها: «رئیس دانشکده کیه؟»، «معاون آموزشی کیه؟»، «مدیر گروه هوش مصنوعی و نرم‌افزار کیست؟».",
            "parameters": {
                "type": "object",
                "properties": {
                    "role_title": {
                        "type": "string",
                        "description": "عنوان سمت سازمانی (مثلاً «مدیر گروه هوش مصنوعی و نرم‌افزار»، «معاون آموزشی»، «رئیس دانشکده»)."
                    }
                },
                "required": ["role_title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_building_info",
            "description": "اطلاعات کلی یک ساختمان دانشکده: تعداد طبقات، موقعیت و توضیحات کلی. هر وقت کاربر درباره یک ساختمان به طور کلی پرسید از این تابع استفاده کن. مثال: ساختمان کامپیوتر چند طبقه داره؟ ساختمان قدیمی اساتید کجاست؟ درمورد ساختمان اصلی بگو.",
            "parameters": {
                "type": "object",
                "properties": {
                    "building_name": {
                        "type": "string",
                        "description": "نام ساختمان (مثلاً: ساختمان کامپیوتر، ساختمان قدیمی اساتید، ساختمان اصلی، فضای باز)"
                    }
                },
                "required": ["building_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_course_details",
            "description": "اولویت اول و اصلی برای دریافت اطلاعات هر درس! هرگاه کاربر اطلاعات کلی، تعداد واحد، پیش‌نیاز یا هم‌نیاز یک درس را خواست، فقط و فقط از این ابزار استفاده کن. مثال: ریاضی 1 چند واحده؟ پیش‌نیاز ساختار داده چیه؟\nهشدار: این ابزار ترمِ ارائه درس را مشخص نمی‌کند. فقط اگر کاربر صراحتاً پرسید «این درس در چه ترمی ارائه می‌شود؟»، آنگاه ابزار get_study_plan را فراخوانی کن.",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_name": {
                        "type": "string",
                        "description": "نام درس (مثلاً: ریاضی 1، برنامه‌سازی پیشرفته، ساختار داده)"
                    }
                },
                "required": ["course_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_study_plan",
            "description": "مشاوره برنامه‌ریزی تحصیلی. دارای دو کاربرد اصلی: ۱- دریافت دروس پیشنهادی برای یک شماره ترم خاص (مثلا ترم 2 چی بردارم؟). ۲- پیدا کردن ترم پیشنهادی برای یک نام درس خاص (مثلا درس ساختار داده چه ترمی پیشنهاد می‌شود؟).",
            "parameters": {
                "type": "object",
                "properties": {
                    "semester_number": {
                        "type": "integer",
                        "description": "فقط شماره نیمسال تحصیلی (ترم) به صورت عدد (مثلاً: ترم اول = 1، ترم دو = 2، ترم 3 = 3) - اگر کاربر ترمی را مطرح نکرد این فیلد را ارسال نکن"
                    },
                    "course_name": {
                        "type": "string", 
                        "description": "نام درس - اگر نام درس شامل عدد بود که به حروف نوشته شده بود تو به عدد بنویس (فیزیک یک -> فیزیک 1 یا ریاضی دو -> ریاضی 2) - اگر کاربر درسی را مطرح نکرد این فیلد را ارسال نکن"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_staff_info",
            "description": "این ابزار فقط و فقط مسئول پیدا کردن 'اشخاص' (کارمندان/کارشناسان) و 'مسئولین' فرایندهای اداری است.\nموارد استفاده:\n۱. اگر کاربر نام کارمندی را پرسید (لیست نام‌ها: احمدی، رضایی، کریمی)، مستقیماً از این ابزار استفاده کن.\n۲. اگر کاربر دنبال 'شخصی' می‌گشت که مسئول کارهای اداری و پشتیبانی است (مثل: مسئول وام، مسئول خوابگاه، چه کسی مسئول حذف و اضافه، انتخاب واحد، گواهی اشتغال، سایت کامپیوتر یا کارآموزی است)، این ابزار را فراخوانی کن تا فرد مسئول و محل استقرارش پیدا شود.\nهشدارها:\n- تداخل با مراحل و لینک‌ها: اگر کاربر در مورد 'مراحل'، 'نحوه دریافت'، 'لینک' یا 'راهنمای' یک فرایند (مثل 'مراحل دریافت گواهی اشتغال به تحصیل') پرسید، به هیچ وجه از این ابزار استفاده نکن! برای این موارد باید از ابزار لینک‌ها استفاده کنی. این ابزار منحصراً برای پیدا کردن 'شخص مسئول' کاربرد دارد.\n- اساتید: برای پیدا کردن اساتید هیئت علمی (دکترها) از این ابزار استفاده نکن.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "نام خانوادگی کارمند بدون پیشنود (مثلا 'خانم رضایی' = 'رضایی') یا کلمه کلیدیِ فرایندی که کاربر می‌خواهد انجام دهد (مثل 'وام'، 'سایت'، 'کارآموزی'، 'آموزش')."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_university_link",
            "description": "فقط و فقط برای پیدا کردن 'آدرس سایت‌ها'، 'لینک سامانه‌ها'، 'پورتال‌های آنلاین'، 'مراحل انجام کارها' و 'راهنماهای اجرایی موجود در سایت دانشگاه' استفاده می‌شود.\nموارد استفاده:\n۱. سامانه‌های آموزشی نمونه (مثل سایت بهستان برای انتخاب واحد یا کارنامه).\n۲. وب‌سایت‌های اصلی (مثل سایت دانشکده).\n۳. راهنمای مراحل اجرایی و فرم‌های داخل سایت (مثل 'راهنمای دریافت گواهی اشتغال به تحصیل' یا 'راهنمای حذف اضطراری').\nهشدارها:\n- تداخل با اشخاص مسئول: اگر کاربر به دنبال 'شخص' انجام‌دهنده کار یا اطلاعات تماس کارمندان است، از این ابزار استفاده نکن.\n- تداخل با آیین‌نامه: اگر کاربر درباره 'مفاد آیین‌نامه'، 'شرایط مشروطی' یا 'تبصره‌های آموزشی' پرسید، به هیچ وجه از این ابزار استفاده نکن (باید از اسناد آیین‌نامه/RAG استفاده کنی). این ابزار فقط زمانی کاربرد دارد که کاربر 'لینک'، 'سایت'، 'مراحل' یا 'راهنمای انجام فرایند در سایت' را بخواهد.\n- مکان فیزیکی: برای آدرس فیزیکی (مثل: دفتر آموزش کجاست؟) از search_facility_or_room استفاده کن.\n- اساتید: برای لینک صفحات شخصی اساتید از get_professor_info استفاده کن.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "نام سامانه، خدمت یا فرایندی که کاربر به دنبال لینک یا راهنمای سایت آن است (مثلاً: بهستان، انتخاب واحد، گواهی اشتغال، حذف اضطراری). نکته مهم: اگر کاربر نام دقیق را نگفت، همان کلمات کلیدی عمومی (مثل 'سامانه آموزشی') را اینجا قرار بده. نیازی به کلماتی مثل 'لینک' یا 'سایت' نیست."
                    },
                    "category": {
                        "type": "string",
                        "description": "دسته‌بندی سامانه. تنها مقادیر مجاز: 'راهنماهای آموزشی' و 'سامانه‌ها'. اگر مطمئن نیستی، ارسال نکن."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_educational_rules",
            "description": "پاسخگویی به سوالات مربوط به قوانین دانشگاهی، مفاد آیین‌نامه‌ها، شرایط مشروطی، غیبت، مرخصی تحصیلی، نمرات و تبصره‌های آموزشی. حتماً از این ابزار برای سوالات قانونی و آیین‌نامه‌ای استفاده کن.\nهشدار: اگر کاربر به دنبال 'لینک سایت'، 'پورتال' یا 'راهنمای ثبت‌نام و فرم‌های داخل سایت' بود، از این ابزار استفاده نکن و سراغ get_university_link برو.",
            "parameters": {
                "type": "object",
                "properties": {
                    "corrected_query": {
                        "type": "string",
                        "description": "اگر سوال کاربر یک پرسش مستقیم و عادی است، متن دقیق آن را با اصلاح غلط‌های املایی بنویس و لحن را تغییر نده. اما **اگر کاربر سوال خود را به شکل یک داستان طولانی، با لحن بسیار محاوره‌ای یا همراه با جزئیات شخصی (مثل نمرات قبلی، دعوا با آموزش، تصادف و...) بیان کرده است**، به هیچ وجه کل متن را کپی نکن! در این حالت، موظف هستی داستان را به یک «سوال حقوقی/آموزشی کوتاه، رسمی، خالص و فاقد جزئیات شخصی» ترجمه کنی تا سیستم جستجوگر (Vector DB) با کلمات اضافی مسموم نشود."
                    },
                    "search_tasks": {
                        "type": "array",
                        "description": "لیستی از وظایف جستجو. اگر سوال کاربر تک‌موضوعی است، فقط یک آیتم در این آرایه بساز. اگر سوال مقایسه‌ای یا چندمرحله‌ای است (مثل تفاوت A و B)، آن را به چند آیتم کاملاً مستقل تفکیک کن.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "sub_query": {
                                    "type": "string",
                                    "description": "بخشی از سوال کاربر که در این مرحله باید جستجو شود. ساختار طبیعی و لحن سوال را حفظ کن و فقط آن را مستقل و کامل بنویس."
                                },
                                "expanded_keywords": {
                                    "type": "string",
                                    "description": "کلمات کلیدی فوق‌العاده خالص و فقط متمرکز بر 'موجودیت اصلی' برای موتور جستجو.\nقوانین مرگبار:\n۱. کلماتی مانند 'دانشجو'، 'کارشناسی'، 'پیوسته'، 'ناپیوسته'، 'ترم' و 'نیمسال' را **کاملاً و بدون هیچ استثنایی** حذف کن. (حضور این کلمات جستجو را خراب می‌کند).\n۲. فقط و فقط روی نام قانون یا مشکل (مثل: مرخصی پزشکی، حذف اضطراری، مشروطی) و وضعیت آن (مثل: احتساب سنوات، بدون احتساب) تمرکز کن.\n۳. حداکثر ۳ الی ۵ کلمه کلیدی تولید کن، نه بیشتر."
                                }
                            },
                            "required": ["sub_query", "expanded_keywords"]
                        }
                    }
                },
                "required": ["corrected_query", "search_tasks"]
            }
        }
    }
]


def run_university_chatbot(user_question: str):

    FALLBACK_MESSAGE = "متأسفانه نتوانستم اطلاعات دقیقی در این زمینه پیدا کنم یا متوجه منظور شما نشدم. لطفاً سوال خود را واضح‌تر یا با جزئیات متفاوت‌تری مطرح کنید."

    system_prompt = """تو دستیار هوشمند و مودب دانشکده کامپیوتر دانشگاه صنعتی خواجه نصیرالدین طوسی هستی. مخاطبین تو منحصراً دانشجویان مقطع کارشناسی (به ویژه کارشناسی پیوسته) هستند. به سوالات کاربران به زبان فارسی روان، دقیق و محترمانه پاسخ بده. تو به مجموعه‌ای از ابزارها (Tools) دسترسی داری. برای پاسخ به هر سوال، ابتدا توضیحات (Description) ابزارهایت را با دقت بخوان و مناسب‌ترین ابزار را انتخاب کن.

قوانین مهم برای نحوه پاسخ‌گویی:

۱. عدم توهم: اطلاعاتی مانند ایمیل، آدرس، نام اتاق، شماره تلفن، اطلاعات دروس یا لینک‌ها را از خودت اختراع نکن. پاسخ تو باید دقیقاً بر اساس خروجی ابزارها باشد.
۲. مدیریت لینک‌ها: هر زمان که ابزارها به تو لینکی دادند، موظف هستی آن لینک را عیناً و به صورت کلیک‌شونده (با فرمت مارک‌داون `[نام](لینک)`) در پاسخ قرار دهی. 
۳. مدیریت خطاها: اگر خروجی ابزار شامل کلید "error" بود، به کاربر بگو اطلاعاتی پیدا نشد. اگر خروجی دارای اطلاعات بود، آن را به فارسی روان توضیح بده.

۴. قوانین اختصاصی نمایش برای برخی ابزارها:
- سامانه و لینک‌ها (get_university_link): نتایج این ابزار را منحصراً در قالب یک جدول مارک‌داون با سه ستون «نام سامانه»، «توضیحات» و «لینک ورود» نمایش بده.
- قوانین آموزشی (get_educational_rules): در پاسخ نهایی به کاربر، حتماً شماره ماده و تبصره یافت شده را ذکر کن. از آنجایی که کاربر دانشجوی کارشناسی پیوسته است، در خواندن خروجی ابزار دقت کن و اگر قانونی بین پیوسته و ناپیوسته تفاوت قائل شده بود، فقط بخش مربوط به پیوسته را به کاربر اعلام کن.
- مسیریابی اماکن: خروجی‌های دارای «لینک_مسیریابی» را با ذکر نام مکان در یک خط جدید نمایش بده. مقادیری که با MASK_MAP_ شروع می‌شوند را دقیقاً داخل پرانتز لینک مارک‌داون قرار بده (مثال: 📍 مسیریابی به آموزش: [نشان](MASK_MAP_NESHAN_123) | [بلد](MASK_MAP_BALAD_123)).

۵. استراتژی انتخاب ابزار برای اشخاص و سمت‌ها (بسیار مهم):
- اگر کلمات «رئیس»، «معاون» یا «مدیر گروه» در سوال بود: بدون هیچ شکی مستقیماً ابزار get_role_holder را فراخوانی کن.
- اگر کلمات «کارشناس»، «مسئول» یا نام یک کارمند اداری در سوال بود: ابزار get_staff_info را فراخوانی کن.
- اگر کاربر فقط نام یک استاد/دکتر را پرسید: ابزار get_professor_info را فراخوانی کن.

۶. استراتژی سوالات چندبخشی:
- اگر کاربر درباره چند موجودیت کاملاً مجزا پرسید (مثلاً "کلاس X کجاست و مدیر گروه هوش مصنوعی کیست؟")، ابزارهای مربوطه را به صورت همزمان و موازی فراخوانی کن.
- اگر کاربر چند ویژگی از یک موضوع واحد را پرسید (مثلاً "درس هوش مصنوعی چند واحده و پیش‌نیاز داره؟")، ابزار مربوطه را فقط یک بار فراخوانی کن.

۷. استراتژی مدیریت سوالات داستانی و محاوره‌ای (بسیار مهم):
- تشخیص احوال‌پرسی: اگر پیام کاربر صرفاً احوال‌پرسی یا کاملاً بی‌ربط بود، ابزاری فراخوانی نکن و فقط مودبانه بخواه سوال آموزشی بپرسد.
- الزام به استخراج از داستان: اما اگر کاربر سوال خود را به شکل یک داستان طولانی، تجربه شخصی یا با لحن محاوره‌ای بیان کرد، هرگز از پاسخ دادن طفره نرو و حتماً ابزار جستجو را فراخوانی کن.
- نحوه ارسال به ابزار: در زمان فراخوانی ابزار برای داستان‌ها، هرگز متن اصلی کاربر را در هیچ‌کدام از پارامترها (به خصوص در پارامتر corrected_query) کپی نکن. تو موظف هستی ابتدا داستان را به یک «سوال حقوقی/رسمی، کوتاه و فاقد کلمات اضافی» ترجمه کنی و منحصراً همان جمله کوتاه و خالص را به عنوان corrected_query ارسال کنی. هیچ‌گونه نویز، اعداد بی‌ربط یا احساساتی نباید به ابزار فرستاده شود.

۸. قوانین قالب‌بندی و فاصله‌گذاری (Typography):
- بین پاراگراف‌ها یا موضوعات مجزا، فقط و فقط «یک خط خالی» فاصله بگذار تا متن خوانا باشد. از ایجاد فاصله‌های دو یا چند خطی اکیداً خودداری کن.
- در زمان استفاده از لیست‌ها (Bullet points)، بین آیتم‌های لیست هیچ‌گونه خط خالی قرار نده؛ آیتم‌های یک لیست باید کاملاً منسجم و زیر هم نوشته شوند.

دقت کن: پارامترها را دقیقاً به شکل یک JSON Object استاندارد بفرست. به توضیحات (Description) هر ابزار اعتماد کن و در انتخاب ابزار جسور باش!
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_question}
    ]

    print(f"User: {user_question}")
    
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0,
        max_tokens=1024
    )

    response_message = response.choices[0].message
    tool_calls = response_message.tool_calls

    if tool_calls:
        messages.append(response_message)
        
        available_functions = {
            "get_professor_info": get_professor_info,
            "search_facility_or_room": search_facility_or_room,
            "get_role_holder": get_role_holder,
            "get_building_info": get_building_info,
            "get_course_details": get_course_details,
            "get_study_plan": get_study_plan,
            "get_staff_info": get_staff_info,
            "get_university_link": get_university_link,
            "get_educational_rules": get_educational_rules,
        }

        for tool_call in tool_calls:
            function_name = tool_call.function.name
            function_to_call = available_functions.get(function_name)
            
            if not function_to_call:
                continue

            function_args = json.loads(tool_call.function.arguments)
            print(f"🤖 [System] Calling Tool: {function_name} with args: {function_args}")
            
            if function_name == "get_professor_info":
                function_response = function_to_call(professor_name=function_args.get("professor_name"))
            elif function_name == "search_facility_or_room":
                function_response = function_to_call(
                    target_location=function_args.get("target_location"),
                    building_name=function_args.get("building_name"),
                    floor_number=function_args.get("floor_number")
                )
            elif function_name == "get_role_holder":
                function_response = function_to_call(role_title=function_args.get("role_title"))
            elif function_name == "get_building_info":
                function_response = function_to_call(building_name=function_args.get("building_name"))
            elif function_name == "get_course_details":
                function_response = function_to_call(course_name=function_args.get("course_name"))
            elif function_name == "get_study_plan":
                function_response = function_to_call(
                    semester_number = function_args.get("semester_number"),
                    course_name = function_args.get("course_name")
                )
            elif function_name == "get_staff_info":
                function_response = function_to_call(query=function_args.get("query"))
            elif function_name == "get_university_link":
                function_response = function_to_call(
                    query=function_args.get("query"),
                    category=function_args.get("category")
                )
            elif function_name == "get_educational_rules":
                function_response = function_to_call(
                    corrected_query=function_args.get("corrected_query", user_question),
                    search_tasks=function_args.get("search_tasks", [])
                )
            
            
            print(f"🤖 [System] Tool returned: {function_response}")

            messages.append(
                {
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": function_response,
                }
            )

        final_response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0 
        )
        final_text = final_response.choices[0].message.content

        if final_text is None or str(final_text).strip() == "":
            return FALLBACK_MESSAGE
        
        if final_text and "MASK_" in final_text:

            if "MASK_MAP_" in final_text:
                map_masks = re.findall(r'MASK_MAP_(NESHAN|BALAD)_([0-9\.]+)_([0-9\.]+)', final_text)
                
                for map_type, lat, lng in set(map_masks):
                    full_mask = f"MASK_MAP_{map_type}_{lat}_{lng}"
                    if map_type == "NESHAN":
                        real_url = f"https://nshn.ir/?lat={lat}&lng={lng}"
                    elif map_type == "BALAD":
                        real_url = f"https://balad.ir/location?latitude={lat}&longitude={lng}"
                    
                    final_text = final_text.replace(full_mask, real_url)

                final_text = final_text.replace("https://balad.ir/https://balad.ir/", "https://balad.ir/")
                final_text = final_text.replace("https://nshn.ir/https://nshn.ir/", "https://nshn.ir/")

            link_mask_ids = re.findall(r'MASK_(?!MAP_)([a-zA-Z0-9_-]+)', final_text)
            
            if link_mask_ids:
                for mask_id in set(link_mask_ids):
                    full_mask = f"MASK_{mask_id}"
                    real_url = LINKS_MAP.get(mask_id, '#')
                    final_text = final_text.replace(full_mask, real_url)
        
        return final_text
    else:
        direct_response = response_message.content
        if direct_response is None or str(direct_response).strip() == "":
            return FALLBACK_MESSAGE
            
        return direct_response

if __name__ == "__main__":
    pass
    