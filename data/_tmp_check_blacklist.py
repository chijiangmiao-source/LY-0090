from config import query_one, query_all
print(query_one("SELECT to_regclass('public.blacklist') AS t1, to_regclass('public.system_config') AS t2"))
print(query_all("SELECT column_name FROM information_schema.columns WHERE table_name='blacklist' ORDER BY ordinal_position"))
