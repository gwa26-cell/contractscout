-- 10 тестовых заявок: 4 срочных, 3 средних, 3 низких
-- Выполнить в pgAdmin или: docker compose exec db psql -U scout -d contractscout_hw -f /path

INSERT INTO orders (service_id, client_name, client_email, client_phone, comment, priority, lead_temperature)
SELECT 1, 'Клиент A', 'a@example.com', '+79990000001', 'Срочно нужна проверка', 1, 'hot'
WHERE NOT EXISTS (SELECT 1 FROM orders WHERE client_email='a@example.com');

INSERT INTO orders (service_id, client_name, client_email, client_phone, comment, priority, lead_temperature)
SELECT 2, 'Клиент B', 'b@example.com', '+79990000002', 'Срочно собрать договор', 1, 'hot'
WHERE NOT EXISTS (SELECT 1 FROM orders WHERE client_email='b@example.com');

INSERT INTO orders (service_id, client_name, client_email, client_phone, comment, priority, lead_temperature)
SELECT 1, 'Клиент C', 'c@example.com', '+79990000003', 'Немедленно проверить риски', 1, 'hot'
WHERE NOT EXISTS (SELECT 1 FROM orders WHERE client_email='c@example.com');

INSERT INTO orders (service_id, client_name, client_email, client_phone, comment, priority, lead_temperature)
SELECT 3, 'Клиент D', 'd@example.com', '+79990000004', 'Срочно в архив', 1, 'hot'
WHERE NOT EXISTS (SELECT 1 FROM orders WHERE client_email='d@example.com');

INSERT INTO orders (service_id, client_name, client_email, client_phone, comment, priority, lead_temperature)
SELECT 2, 'Клиент E', 'e@example.com', '+79990000005', 'Черновик на следующей неделе', 2, 'warm'
WHERE NOT EXISTS (SELECT 1 FROM orders WHERE client_email='e@example.com');

INSERT INTO orders (service_id, client_name, client_email, client_phone, comment, priority, lead_temperature)
SELECT 1, 'Клиент F', 'f@example.com', '+79990000006', 'Проверка без спешки', 2, 'warm'
WHERE NOT EXISTS (SELECT 1 FROM orders WHERE client_email='f@example.com');

INSERT INTO orders (service_id, client_name, client_email, client_phone, comment, priority, lead_temperature)
SELECT 4, 'Клиент G', 'g@example.com', '+79990000007', 'Исправить по рискам', 2, 'warm'
WHERE NOT EXISTS (SELECT 1 FROM orders WHERE client_email='g@example.com');

INSERT INTO orders (service_id, client_name, client_email, client_phone, comment, priority, lead_temperature)
SELECT 5, 'Клиент H', 'h@example.com', '+79990000008', 'Когда будет время', 3, 'cold'
WHERE NOT EXISTS (SELECT 1 FROM orders WHERE client_email='h@example.com');

INSERT INTO orders (service_id, client_name, client_email, client_phone, comment, priority, lead_temperature)
SELECT 3, 'Клиент I', 'i@example.com', '+79990000009', 'Низкий приоритет', 3, 'cold'
WHERE NOT EXISTS (SELECT 1 FROM orders WHERE client_email='i@example.com');

INSERT INTO orders (service_id, client_name, client_email, client_phone, comment, priority, lead_temperature)
SELECT 2, 'Клиент J', 'j@example.com', '+79990000010', 'Позже', 3, 'cold'
WHERE NOT EXISTS (SELECT 1 FROM orders WHERE client_email='j@example.com');
