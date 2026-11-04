-- Assign the missing port/road mode of one book; never overwrite it or change money.
BEGIN;
SET LOCAL ROLE sokhach_owner;
CREATE OR REPLACE FUNCTION sokhach.set_customer_transport(
 customer_id bigint, expected_version bigint, idempotency_key text, transport_mode text
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,sokhach,pg_temp AS $$
DECLARE v_payload jsonb:=jsonb_build_object('command','set_customer_transport','transport_mode',transport_mode);
 v_retry jsonb; v_before jsonb; v_after jsonb;
BEGIN
 v_retry:=sokhach._begin_command(customer_id,expected_version,idempotency_key,v_payload);
 IF v_retry IS NOT NULL THEN RETURN v_retry; END IF;
 IF transport_mode IS NULL OR transport_mode NOT IN ('CANG','BO') THEN RAISE EXCEPTION 'INVALID_COMMAND'; END IF;
 SELECT to_jsonb(c) INTO v_before FROM sokhach.customer c WHERE c.id=customer_id;
 IF v_before->>'commodity_id' IS NULL OR v_before->>'transport_mode' IS NOT NULL THEN RAISE EXCEPTION 'STALE_LEDGER'; END IF;
 UPDATE sokhach.customer c SET transport_mode=set_customer_transport.transport_mode WHERE c.id=customer_id RETURNING to_jsonb(c) INTO v_after;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after",idempotency_key)
 VALUES(customer_id,'customer_attr',sokhach._actor(),jsonb_build_object('customer',v_before),
  jsonb_build_object('customer',v_after,'transport_mode',set_customer_transport.transport_mode),idempotency_key);
 RETURN sokhach._finish_command(customer_id,idempotency_key,v_payload,jsonb_build_object('transport_mode',set_customer_transport.transport_mode));
END $$;
REVOKE ALL ON FUNCTION sokhach.set_customer_transport(bigint,bigint,text,text) FROM PUBLIC,sokhach_reader;
GRANT EXECUTE ON FUNCTION sokhach.set_customer_transport(bigint,bigint,text,text) TO sokhach_app;
COMMIT;
