from bottle import Bottle, template, request, response, redirect, static_file, abort
from bottle.ext import beaker
from jinja2 import Environment, FileSystemLoader
import os
from datetime import datetime, timedelta

from config import SECRET_KEY
from utils import format_datetime, format_date, format_time, get_status_text, get_status_class
import auth
import stores as store_module
import courses as course_module
import registrations as reg_module
import stats as stats_module


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)
env.filters['datetime'] = format_datetime
env.filters['date'] = format_date
env.filters['time'] = format_time
env.filters['status_text'] = get_status_text
env.filters['status_class'] = get_status_class


def render(tpl_name, **kwargs):
    tpl = env.get_template(tpl_name + '.html')
    current_user = auth.get_current_user()
    kwargs['current_user'] = current_user
    kwargs['now'] = datetime.now()
    kwargs['request'] = request
    return tpl.render(**kwargs)


def render_detail_registrations(course_id, prefix_msg=None):
    course = course_module.get_course(course_id)
    normal_regs = course_module.get_course_normal_registrations(course_id)
    waitlist = course_module.get_course_waitlist(course_id)
    normal_count = course_module.get_normal_registration_count(course_id)
    waitlist_count = course_module.get_waitlist_count(course_id)
    regs_tpl = env.get_template('courses/detail_registrations.html')
    regs_content = regs_tpl.render(
        course=course, normal_regs=normal_regs, waitlist=waitlist,
        normal_count=normal_count, waitlist_count=waitlist_count,
        datetime=format_datetime, status_text=get_status_text, status_class=get_status_class
    )
    msg_html = ''
    if prefix_msg:
        msg_html = f'<div id="reg-msg"><div class="alert alert-success alert-dismissible fade show mb-3">{prefix_msg}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div></div>'
    else:
        msg_html = '<div id="reg-msg"></div>'
    return msg_html + f'<div id="regs-container" hx-swap-oob="innerHTML:#regs-container">{regs_content}</div>'


def render_error_msg(msg):
    return f'<div id="reg-msg"><div class="alert alert-danger alert-dismissible fade show mb-3">{msg}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div></div>'


session_opts = {
    'session.type': 'file',
    'session.cookie_expires': 3600 * 8,
    'session.data_dir': './data/sessions',
    'session.auto': True,
    'session.key': 'gym_class_session',
    'session.secret': SECRET_KEY,
    'session.httponly': True,
    'session.samesite': 'lax',
}


def make_app():
    _app = Bottle()
    app = beaker.middleware.SessionMiddleware(_app, session_opts)

    @_app.hook('after_request')
    def _set_charset():
        content_type = response.content_type
        if content_type and 'text/' in content_type and 'charset' not in content_type:
            response.content_type = content_type + '; charset=UTF-8'
        elif not content_type:
            response.content_type = 'text/html; charset=UTF-8'

    @_app.hook('before_request')
    def _auto_update_course_status():
        if request.path.startswith('/static/') or request.path == '/login':
            return
        try:
            course_module.update_course_status_auto()
        except Exception:
            pass

    @_app.route('/static/<filepath:path>')
    def server_static(filepath):
        return static_file(filepath, root=STATIC_DIR)

    @_app.route('/')
    @auth.require_login
    def index():
        today = datetime.now().date()
        today_from = datetime.combine(today, datetime.min.time())
        today_to = datetime.combine(today, datetime.max.time())
        today_courses = course_module.list_courses(date_from=today_from, date_to=today_to)
        return render('index', today_courses=today_courses)

    @_app.route('/login', method=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.forms.get('username', '').strip()
            password = request.forms.get('password', '').strip()
            if not username or not password:
                return render('login', error='请输入用户名和密码', username=username)
            user, err = auth.login_user(username, password)
            if err:
                return render('login', error=err, username=username)
            return redirect('/')
        if auth.get_current_user():
            return redirect('/')
        return render('login', error=None, username='')

    @_app.route('/logout')
    def logout():
        auth.logout_user()
        return redirect('/login')

    @_app.route('/stores')
    @auth.require_login
    def list_stores():
        all_stores = store_module.list_stores()
        return render('stores/list', stores=all_stores, error=None, success=None)

    @_app.route('/stores/create', method=['GET', 'POST'])
    @auth.require_login
    def create_store():
        if request.method == 'POST':
            name = request.forms.get('name', '').strip()
            address = request.forms.get('address', '').strip() or None
            phone = request.forms.get('phone', '').strip() or None
            store, err = store_module.create_store(name, address, phone)
            if request.headers.get('HX-Request'):
                if err:
                    return f'<div class="alert alert-danger">{err}</div>'
                return _render_store_row(store)
            all_stores = store_module.list_stores()
            return render('stores/list', stores=all_stores, error=err, success=None)
        return render('stores/form', store=None, error=None)

    @_app.route('/stores/<store_id:int>/edit', method=['GET', 'POST'])
    @auth.require_login
    def edit_store(store_id):
        store = store_module.get_store(store_id)
        if not store:
            abort(404)
        if request.method == 'POST':
            name = request.forms.get('name', '').strip() or None
            address = request.forms.get('address', '').strip()
            address = address if address != '' else None
            phone = request.forms.get('phone', '').strip()
            phone = phone if phone != '' else None
            updated, err = store_module.update_store(store_id, name, address, phone)
            if request.headers.get('HX-Request'):
                if err:
                    return f'<div class="alert alert-danger">{err}</div>'
                return _render_store_row(updated)
            all_stores = store_module.list_stores()
            return render('stores/list', stores=all_stores, error=err, success=None)
        return render('stores/form', store=store, error=None)

    @_app.route('/stores/<store_id:int>/delete', method=['POST'])
    @auth.require_login
    def delete_store(store_id):
        success, err = store_module.delete_store(store_id)
        if request.headers.get('HX-Request'):
            if err:
                return f'<div class="alert alert-danger">{err}</div>'
            return ''
        all_stores = store_module.list_stores()
        return render('stores/list', stores=all_stores, error=err, success=None)

    @_app.route('/classrooms')
    @auth.require_login
    def list_classrooms():
        store_id = request.query.get('store_id', '')
        store_id_int = int(store_id) if store_id and store_id.isdigit() else None
        classrooms = store_module.list_classrooms(store_id_int)
        all_stores = store_module.list_stores()
        return render('classrooms/list', classrooms=classrooms,
                      stores=all_stores, selected_store=store_id_int)

    @_app.route('/classrooms/create', method=['GET', 'POST'])
    @auth.require_login
    def create_classroom():
        all_stores = store_module.list_stores()
        if request.method == 'POST':
            store_id = request.forms.get('store_id', '')
            store_id_int = int(store_id) if store_id.isdigit() else None
            name = request.forms.get('name', '').strip()
            capacity = request.forms.get('capacity', '20')
            capacity_int = int(capacity) if capacity.isdigit() else 20
            description = request.forms.get('description', '').strip() or None
            classroom, err = store_module.create_classroom(store_id_int, name, capacity_int, description)
            if request.headers.get('HX-Request'):
                if err:
                    return f'<div class="alert alert-danger">{err}</div>'
                return _render_classroom_row(classroom)
            classrooms = store_module.list_classrooms()
            return render('classrooms/list', classrooms=classrooms, stores=all_stores, selected_store=None)
        return render('classrooms/form', classroom=None, stores=all_stores, error=None)

    @_app.route('/classrooms/<classroom_id:int>/edit', method=['GET', 'POST'])
    @auth.require_login
    def edit_classroom(classroom_id):
        classroom = store_module.get_classroom(classroom_id)
        all_stores = store_module.list_stores()
        if not classroom:
            abort(404)
        if request.method == 'POST':
            store_id = request.forms.get('store_id', '')
            store_id_int = int(store_id) if store_id.isdigit() else None
            name = request.forms.get('name', '').strip() or None
            capacity = request.forms.get('capacity', '')
            capacity_int = int(capacity) if capacity.isdigit() else None
            description = request.forms.get('description', '').strip()
            description = description if description != '' else None
            updated, err = store_module.update_classroom(classroom_id, store_id_int, name, capacity_int, description)
            if request.headers.get('HX-Request'):
                if err:
                    return f'<div class="alert alert-danger">{err}</div>'
                return _render_classroom_row(updated)
            classrooms = store_module.list_classrooms()
            return render('classrooms/list', classrooms=classrooms, stores=all_stores, selected_store=None)
        return render('classrooms/form', classroom=classroom, stores=all_stores, error=None)

    @_app.route('/classrooms/<classroom_id:int>/delete', method=['POST'])
    @auth.require_login
    def delete_classroom(classroom_id):
        success, err = store_module.delete_classroom(classroom_id)
        if request.headers.get('HX-Request'):
            if err:
                return f'<div class="alert alert-danger">{err}</div>'
            return ''
        classrooms = store_module.list_classrooms()
        all_stores = store_module.list_stores()
        return render('classrooms/list', classrooms=classrooms, stores=all_stores, selected_store=None)

    @_app.route('/courses')
    @auth.require_login
    def list_courses():
        store_id = request.query.get('store_id', '')
        status = request.query.get('status', '')
        keyword = request.query.get('keyword', '').strip()
        date_from_str = request.query.get('date_from', '')
        date_to_str = request.query.get('date_to', '')
        store_id_int = int(store_id) if store_id and store_id.isdigit() else None
        status_val = status if status else None
        keyword_val = keyword if keyword else None
        date_from = None
        date_to = None
        if date_from_str:
            try:
                date_from = datetime.strptime(date_from_str, '%Y-%m-%d')
            except Exception:
                pass
        if date_to_str:
            try:
                date_to = datetime.strptime(date_to_str, '%Y-%m-%d') + timedelta(days=1)
            except Exception:
                pass
        courses_list = course_module.list_courses(store_id_int, status_val, date_from, date_to, keyword_val)
        all_stores = store_module.list_stores()
        return render('courses/list', courses=courses_list, stores=all_stores,
                      selected_store=store_id_int, selected_status=status,
                      keyword=keyword, date_from=date_from_str, date_to=date_to_str)

    @_app.route('/courses/create', method=['GET', 'POST'])
    @auth.require_login
    def create_course():
        all_stores = store_module.list_stores()
        if request.method == 'POST':
            course_name = request.forms.get('course_name', '').strip()
            store_id = request.forms.get('store_id', '')
            store_id_int = int(store_id) if store_id.isdigit() else None
            classroom_id = request.forms.get('classroom_id', '')
            classroom_id_int = int(classroom_id) if classroom_id.isdigit() else None
            start_time_str = request.forms.get('start_time', '').strip()
            end_time_str = request.forms.get('end_time', '').strip() or None
            max_students = request.forms.get('max_students', '')
            max_students_int = int(max_students) if max_students.isdigit() else None
            instructor = request.forms.get('instructor', '').strip() or None
            course, err = course_module.create_course(
                course_name, store_id_int, classroom_id_int, start_time_str,
                max_students_int, instructor, end_time_str
            )
            if request.headers.get('HX-Request'):
                if err:
                    return f'<div class="alert alert-danger">{err}</div>'
                return _render_course_row(course)
            courses_list = course_module.list_courses()
            return render('courses/list', courses=courses_list, stores=all_stores,
                          selected_store=None, selected_status='', keyword='',
                          date_from='', date_to='')
        classrooms = store_module.list_classrooms()
        return render('courses/form', course=None, stores=all_stores, classrooms=classrooms, error=None)

    @_app.route('/courses/<course_id:int>/edit', method=['GET', 'POST'])
    @auth.require_login
    def edit_course(course_id):
        course = course_module.get_course(course_id)
        all_stores = store_module.list_stores()
        if not course:
            abort(404)
        if request.method == 'POST':
            course_name = request.forms.get('course_name', '').strip() or None
            store_id = request.forms.get('store_id', '')
            store_id_int = int(store_id) if store_id.isdigit() else None
            classroom_id = request.forms.get('classroom_id', '')
            classroom_id_int = int(classroom_id) if classroom_id.isdigit() else None
            start_time_str = request.forms.get('start_time', '').strip() or None
            end_time_str = request.forms.get('end_time', '').strip() or None
            max_students = request.forms.get('max_students', '')
            max_students_int = int(max_students) if max_students.isdigit() else None
            instructor = request.forms.get('instructor', '').strip()
            instructor = instructor if instructor != '' else None
            updated, err = course_module.update_course(
                course_id, course_name, store_id_int, classroom_id_int,
                start_time_str, end_time_str, max_students_int, None, instructor
            )
            if request.headers.get('HX-Request'):
                if err:
                    return f'<div class="alert alert-danger">{err}</div>'
                return _render_course_row(updated)
            courses_list = course_module.list_courses()
            return render('courses/list', courses=courses_list, stores=all_stores,
                          selected_store=None, selected_status='', keyword='',
                          date_from='', date_to='')
        classrooms = store_module.list_classrooms(course['store_id'])
        return render('courses/form', course=course, stores=all_stores, classrooms=classrooms, error=None)

    @_app.route('/courses/<course_id:int>/delete', method=['POST'])
    @auth.require_login
    def delete_course(course_id):
        success, err = course_module.delete_course(course_id)
        if request.headers.get('HX-Request'):
            if err:
                return f'<div class="alert alert-danger">{err}</div>'
            return ''
        courses_list = course_module.list_courses()
        all_stores = store_module.list_stores()
        return render('courses/list', courses=courses_list, stores=all_stores,
                      selected_store=None, selected_status='', keyword='',
                      date_from='', date_to='')

    @_app.route('/courses/<course_id:int>/cancel', method=['POST'])
    @auth.require_login
    def cancel_course(course_id):
        updated, err = course_module.update_course(course_id, status='cancelled')
        if request.headers.get('HX-Request'):
            if err:
                return f'<div class="alert alert-danger">{err}</div>'
            return _render_course_row(updated)
        redirect(f'/courses/{course_id}')

    @_app.route('/courses/<course_id:int>')
    @auth.require_login
    def course_detail(course_id):
        course = course_module.get_course(course_id)
        if not course:
            abort(404)
        normal_regs = course_module.get_course_normal_registrations(course_id)
        waitlist = course_module.get_course_waitlist(course_id)
        normal_count = course_module.get_normal_registration_count(course_id)
        waitlist_count = course_module.get_waitlist_count(course_id)
        return render('courses/detail', course=course, normal_regs=normal_regs,
                      waitlist=waitlist, normal_count=normal_count, waitlist_count=waitlist_count)

    @_app.route('/classrooms/by_store/<store_id:int>')
    @auth.require_login
    def classrooms_by_store(store_id):
        classrooms = store_module.list_classrooms(store_id)
        options = '<option value="">请选择教室</option>'
        for c in classrooms:
            options += f'<option value="{c["id"]}">{c["name"]} (容量:{c["capacity"]})</option>'
        return options

    @_app.route('/registrations')
    @auth.require_login
    def list_registrations():
        course_id = request.query.get('course_id', '')
        phone = request.query.get('member_phone', '').strip()
        status = request.query.get('status', '')
        course_id_int = int(course_id) if course_id and course_id.isdigit() else None
        phone_val = phone if phone else None
        status_val = status if status else None
        regs = reg_module.list_registrations(course_id_int, phone_val, status_val)
        all_courses = course_module.list_courses()
        return render('registrations/list', registrations=regs, courses=all_courses,
                      selected_course=course_id_int, phone=phone, selected_status=status)

    @_app.route('/registrations/create', method=['POST'])
    @auth.require_login
    def create_registration():
        course_id = request.forms.get('course_id', '')
        course_id_int = int(course_id) if course_id.isdigit() else None
        member_name = request.forms.get('member_name', '').strip()
        member_phone = request.forms.get('member_phone', '').strip()
        reg, msg = reg_module.create_registration(course_id_int, member_name, member_phone)
        if request.headers.get('HX-Request'):
            if not reg:
                return render_error_msg(msg)
            is_htmx_detail = request.forms.get('from_detail', '')
            if is_htmx_detail:
                return render_detail_registrations(course_id_int, msg)
            return f'<div class="alert alert-success">{msg}</div>'
        redirect(f'/courses/{course_id_int}' if course_id_int else '/registrations')

    @_app.route('/registrations/<reg_id:int>/checkin', method=['POST'])
    @auth.require_login
    def checkin_registration(reg_id):
        reg, msg = reg_module.checkin_registration(reg_id)
        if request.headers.get('HX-Request'):
            if not reg:
                return render_error_msg(msg)
            return render_detail_registrations(reg['course_id'], msg)
        redirect(f'/courses/{reg["course_id"]}')

    @_app.route('/registrations/checkin_by_phone', method=['POST'])
    @auth.require_login
    def checkin_by_phone():
        course_id = request.forms.get('course_id', '')
        course_id_int = int(course_id) if course_id.isdigit() else None
        phone = request.forms.get('member_phone', '').strip()
        reg, msg = reg_module.checkin_by_phone(course_id_int, phone)
        if request.headers.get('HX-Request'):
            if not reg:
                return render_error_msg(msg)
            full_msg = f'{msg} - {reg["member_name"]}'
            return render_detail_registrations(course_id_int, full_msg)
        redirect(f'/courses/{course_id_int}')

    @_app.route('/registrations/<reg_id:int>/dropout', method=['POST'])
    @auth.require_login
    def dropout_registration(reg_id):
        result, msg = reg_module.dropout_registration(reg_id)
        if request.headers.get('HX-Request'):
            if not result:
                return render_error_msg(msg)
            return render_detail_registrations(result['course_id'], msg)
        redirect(f'/courses/{result["course_id"]}')

    @_app.route('/registrations/<reg_id:int>/promote', method=['POST'])
    @auth.require_login
    def promote_waitlist(reg_id):
        reg, msg = reg_module.promote_waitlist(reg_id)
        if request.headers.get('HX-Request'):
            if not reg:
                return render_error_msg(msg)
            return render_detail_registrations(reg['course_id'], msg)
        redirect(f'/courses/{reg["course_id"]}')

    @_app.route('/registrations/<reg_id:int>/no_show', method=['POST'])
    @auth.require_login
    def mark_no_show(reg_id):
        reg, msg = reg_module.mark_no_show(reg_id)
        if request.headers.get('HX-Request'):
            if not reg:
                return render_error_msg(msg)
            return render_detail_registrations(reg['course_id'], msg)
        redirect(f'/courses/{reg["course_id"]}')

    @_app.route('/courses/<course_id:int>/process_no_shows', method=['POST'])
    @auth.require_login
    def process_no_shows(course_id):
        count = reg_module.process_no_shows_for_course(course_id)
        if request.headers.get('HX-Request'):
            return render_detail_registrations(course_id, f'已批量处理完成，共标记{count}人失约')
        redirect(f'/courses/{course_id}')

    @_app.route('/stats')
    @auth.require_login
    def view_stats():
        store_id = request.query.get('store_id', '')
        date_from_str = request.query.get('date_from', '')
        date_to_str = request.query.get('date_to', '')
        store_id_int = int(store_id) if store_id and store_id.isdigit() else None
        date_from = None
        date_to = None
        if date_from_str:
            try:
                date_from = datetime.strptime(date_from_str, '%Y-%m-%d')
            except Exception:
                pass
        if date_to_str:
            try:
                date_to = datetime.strptime(date_to_str, '%Y-%m-%d') + timedelta(days=1)
            except Exception:
                pass
        overall = stats_module.get_overall_stats(store_id_int, date_from, date_to)
        no_show_rank = stats_module.get_member_no_show_ranking(store_id_int, date_from, date_to)
        course_stats = stats_module.get_course_stats_list(store_id_int, date_from, date_to)
        store_comp = stats_module.get_store_comparison(date_from, date_to)
        all_stores = store_module.list_stores()
        return render('stats/index', overall=overall, no_show_rank=no_show_rank,
                      course_stats=course_stats, store_comp=store_comp, stores=all_stores,
                      selected_store=store_id_int, date_from=date_from_str, date_to=date_to_str)

    @_app.error(404)
    def error404(error):
        return render('errors/404'), 404

    @_app.error(500)
    def error500(error):
        return render('errors/500', error=error), 500

    return _app, app


def _render_store_row(store):
    tpl = env.get_template('stores/_row.html')
    return tpl.render(store=store, datetime=format_datetime)


def _render_classroom_row(classroom):
    tpl = env.get_template('classrooms/_row.html')
    return tpl.render(classroom=classroom, datetime=format_datetime, status_text=get_status_text)


def _render_course_row(course):
    from config import get_db_connection, get_db_cursor
    with get_db_connection() as conn:
        cur = get_db_cursor(conn)
        cur.execute("""
            SELECT COUNT(*) as cnt FROM registrations
            WHERE course_id = %s AND is_waitlist = FALSE AND status NOT IN ('dropped', 'frozen')
        """, (course['id'],))
        normal_count = cur.fetchone()['cnt']
        cur.execute("""
            SELECT COUNT(*) as cnt FROM registrations
            WHERE course_id = %s AND is_waitlist = TRUE AND status = 'waitlist'
        """, (course['id'],))
        waitlist_count = cur.fetchone()['cnt']
    tpl = env.get_template('courses/_row.html')
    return tpl.render(course=course, normal_count=normal_count, waitlist_count=waitlist_count,
                      datetime=format_datetime, status_text=get_status_text, status_class=get_status_class)


if __name__ == '__main__':
    _app, app = make_app()
    from wsgiref.simple_server import make_server
    server = make_server('0.0.0.0', 8080, app)
    server.serve_forever()
