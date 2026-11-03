-- Assign the missing commodity of one book; never merge books or change money.
BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE OR REPLACE FUNCTION sokhach.set_customer_commodity(
 customer_id bigint, expected_version bigint, idempotency_key text, commodity_name text
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','set_customer_commodity','commodity_name',commodity_name);
 v_retry jsonb; v_before jsonb; v_after jsonb; v_commodity bigint;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 IF commodity_name IS NULL OR commodity_name NOT IN ('Sầu riêng','Thanh long','Chuối','Mít','Dừa')
 THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 SELECT to_jsonb(c) INTO v_before FROM sokhach.customer c WHERE c.id=customer_id;
 IF v_before->>'commodity_id' IS NOT NULL THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
 INSERT INTO sokhach.commodity(name) VALUES(commodity_name) ON CONFLICT(name) DO NOTHING;
 SELECT id INTO v_commodity FROM sokhach.commodity WHERE name=commodity_name;
 UPDATE sokhach.customer c SET commodity_id=v_commodity WHERE c.id=customer_id RETURNING to_jsonb(c) INTO v_after;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(customer_id,'customer_attr',sokhach._actor(),jsonb_build_object('customer',v_before),
  jsonb_build_object('customer',v_after,'commodity_name',commodity_name),idempotency_key);
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('commodity',commodity_name));
END $$;
REVOKE ALL ON FUNCTION sokhach.set_customer_commodity(bigint,bigint,text,text) FROM PUBLIC,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.set_customer_commodity(bigint,bigint,text,text) TO sokhach_app;
COMMIT;
