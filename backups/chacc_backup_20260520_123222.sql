--
-- PostgreSQL database dump
--

\restrict LInjkiKLzXTPLNxl7uSQ83I3J9VortzbSyttc38Xn4MHmtme1bv5geSU78f5dMg

-- Dumped from database version 16.13 (Ubuntu 16.13-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.13 (Ubuntu 16.13-0ubuntu0.24.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: actiontype; Type: TYPE; Schema: public; Owner: opentz
--

CREATE TYPE public.actiontype AS ENUM (
    'add_menu_item',
    'edit_menu_item',
    'update_price',
    'update_stock',
    'publish_menu',
    'unpublish_menu',
    'create_offer',
    'edit_offer',
    'delete_offer',
    'create_event_pricing',
    'edit_event_pricing'
);


ALTER TYPE public.actiontype OWNER TO opentz;

--
-- Name: offertype; Type: TYPE; Schema: public; Owner: opentz
--

CREATE TYPE public.offertype AS ENUM (
    'percentage',
    'fixed_amount',
    'buy_x_get_y',
    'free_delivery'
);


ALTER TYPE public.offertype OWNER TO opentz;

--
-- Name: orderstatus; Type: TYPE; Schema: public; Owner: opentz
--

CREATE TYPE public.orderstatus AS ENUM (
    'pending',
    'confirmed',
    'preparing',
    'ready_for_pickup',
    'out_for_delivery',
    'delivered',
    'cancelled'
);


ALTER TYPE public.orderstatus OWNER TO opentz;

--
-- Name: ordertype; Type: TYPE; Schema: public; Owner: opentz
--

CREATE TYPE public.ordertype AS ENUM (
    'delivery',
    'pickup'
);


ALTER TYPE public.ordertype OWNER TO opentz;

--
-- Name: paymentmethod; Type: TYPE; Schema: public; Owner: opentz
--

CREATE TYPE public.paymentmethod AS ENUM (
    'cash',
    'card',
    'online'
);


ALTER TYPE public.paymentmethod OWNER TO opentz;

--
-- Name: paymentstatus; Type: TYPE; Schema: public; Owner: opentz
--

CREATE TYPE public.paymentstatus AS ENUM (
    'pending',
    'paid'
);


ALTER TYPE public.paymentstatus OWNER TO opentz;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: chacc_migration_log; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.chacc_migration_log (
    id integer NOT NULL,
    version_num character varying(64) NOT NULL,
    description text,
    checksum character varying(64),
    applied_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    rollback_available boolean DEFAULT false
);


ALTER TABLE public.chacc_migration_log OWNER TO opentz;

--
-- Name: chacc_migration_log_id_seq; Type: SEQUENCE; Schema: public; Owner: opentz
--

CREATE SEQUENCE public.chacc_migration_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.chacc_migration_log_id_seq OWNER TO opentz;

--
-- Name: chacc_migration_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: opentz
--

ALTER SEQUENCE public.chacc_migration_log_id_seq OWNED BY public.chacc_migration_log.id;


--
-- Name: menu_activity_logs; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.menu_activity_logs (
    user_id integer NOT NULL,
    restaurant_id integer NOT NULL,
    action_type public.actiontype NOT NULL,
    details character varying,
    ip_address character varying(45),
    id integer NOT NULL,
    uuid uuid NOT NULL
);


ALTER TABLE public.menu_activity_logs OWNER TO opentz;

--
-- Name: menu_activity_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: opentz
--

CREATE SEQUENCE public.menu_activity_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.menu_activity_logs_id_seq OWNER TO opentz;

--
-- Name: menu_activity_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: opentz
--

ALTER SEQUENCE public.menu_activity_logs_id_seq OWNED BY public.menu_activity_logs.id;


--
-- Name: menu_cart_items; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.menu_cart_items (
    cart_id integer NOT NULL,
    menu_item_id integer NOT NULL,
    quantity integer NOT NULL,
    unit_price numeric(10,2) NOT NULL,
    id integer NOT NULL,
    uuid uuid NOT NULL
);


ALTER TABLE public.menu_cart_items OWNER TO opentz;

--
-- Name: menu_cart_items_id_seq; Type: SEQUENCE; Schema: public; Owner: opentz
--

CREATE SEQUENCE public.menu_cart_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.menu_cart_items_id_seq OWNER TO opentz;

--
-- Name: menu_cart_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: opentz
--

ALTER SEQUENCE public.menu_cart_items_id_seq OWNED BY public.menu_cart_items.id;


--
-- Name: menu_carts; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.menu_carts (
    customer_id integer NOT NULL,
    restaurant_id integer NOT NULL,
    id integer NOT NULL,
    uuid uuid NOT NULL
);


ALTER TABLE public.menu_carts OWNER TO opentz;

--
-- Name: menu_carts_id_seq; Type: SEQUENCE; Schema: public; Owner: opentz
--

CREATE SEQUENCE public.menu_carts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.menu_carts_id_seq OWNER TO opentz;

--
-- Name: menu_carts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: opentz
--

ALTER SEQUENCE public.menu_carts_id_seq OWNED BY public.menu_carts.id;


--
-- Name: menu_categories; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.menu_categories (
    restaurant_id integer NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    display_order integer NOT NULL,
    image_url character varying(500),
    id integer NOT NULL,
    uuid uuid NOT NULL
);


ALTER TABLE public.menu_categories OWNER TO opentz;

--
-- Name: menu_categories_id_seq; Type: SEQUENCE; Schema: public; Owner: opentz
--

CREATE SEQUENCE public.menu_categories_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.menu_categories_id_seq OWNER TO opentz;

--
-- Name: menu_categories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: opentz
--

ALTER SEQUENCE public.menu_categories_id_seq OWNED BY public.menu_categories.id;


--
-- Name: menu_customers; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.menu_customers (
    user_id integer NOT NULL,
    id integer NOT NULL,
    uuid uuid NOT NULL
);


ALTER TABLE public.menu_customers OWNER TO opentz;

--
-- Name: menu_customers_id_seq; Type: SEQUENCE; Schema: public; Owner: opentz
--

CREATE SEQUENCE public.menu_customers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.menu_customers_id_seq OWNER TO opentz;

--
-- Name: menu_customers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: opentz
--

ALTER SEQUENCE public.menu_customers_id_seq OWNED BY public.menu_customers.id;


--
-- Name: menu_event_pricings; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.menu_event_pricings (
    menu_item_id integer NOT NULL,
    price numeric(10,2) NOT NULL,
    starts_at character varying NOT NULL,
    ends_at character varying NOT NULL,
    name character varying(255),
    is_recurring boolean,
    recurrence_rule character varying(255),
    id integer NOT NULL,
    uuid uuid NOT NULL
);


ALTER TABLE public.menu_event_pricings OWNER TO opentz;

--
-- Name: menu_event_pricings_id_seq; Type: SEQUENCE; Schema: public; Owner: opentz
--

CREATE SEQUENCE public.menu_event_pricings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.menu_event_pricings_id_seq OWNER TO opentz;

--
-- Name: menu_event_pricings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: opentz
--

ALTER SEQUENCE public.menu_event_pricings_id_seq OWNED BY public.menu_event_pricings.id;


--
-- Name: menu_items; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.menu_items (
    restaurant_id integer NOT NULL,
    category_id integer,
    name character varying(255) NOT NULL,
    description text,
    base_price numeric(10,2) NOT NULL,
    current_price numeric(10,2) NOT NULL,
    stock_quantity integer,
    image_url character varying(500),
    is_available boolean NOT NULL,
    preparation_time integer,
    id integer NOT NULL,
    uuid uuid NOT NULL
);


ALTER TABLE public.menu_items OWNER TO opentz;

--
-- Name: menu_items_id_seq; Type: SEQUENCE; Schema: public; Owner: opentz
--

CREATE SEQUENCE public.menu_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.menu_items_id_seq OWNER TO opentz;

--
-- Name: menu_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: opentz
--

ALTER SEQUENCE public.menu_items_id_seq OWNED BY public.menu_items.id;


--
-- Name: menu_offer_items; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.menu_offer_items (
    id integer NOT NULL,
    offer_id integer NOT NULL,
    menu_item_id integer NOT NULL,
    uuid uuid NOT NULL
);


ALTER TABLE public.menu_offer_items OWNER TO opentz;

--
-- Name: menu_offer_items_id_seq; Type: SEQUENCE; Schema: public; Owner: opentz
--

CREATE SEQUENCE public.menu_offer_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.menu_offer_items_id_seq OWNER TO opentz;

--
-- Name: menu_offer_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: opentz
--

ALTER SEQUENCE public.menu_offer_items_id_seq OWNED BY public.menu_offer_items.id;


--
-- Name: menu_offers; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.menu_offers (
    restaurant_id integer,
    name character varying(255) NOT NULL,
    description text,
    offer_type public.offertype NOT NULL,
    discount_value numeric(10,2),
    minimum_order numeric(10,2),
    maximum_discount numeric(10,2),
    starts_at character varying NOT NULL,
    ends_at character varying NOT NULL,
    usage_limit integer,
    is_active boolean NOT NULL,
    id integer NOT NULL,
    uuid uuid NOT NULL
);


ALTER TABLE public.menu_offers OWNER TO opentz;

--
-- Name: menu_offers_id_seq; Type: SEQUENCE; Schema: public; Owner: opentz
--

CREATE SEQUENCE public.menu_offers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.menu_offers_id_seq OWNER TO opentz;

--
-- Name: menu_offers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: opentz
--

ALTER SEQUENCE public.menu_offers_id_seq OWNED BY public.menu_offers.id;


--
-- Name: menu_order_items; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.menu_order_items (
    order_id integer NOT NULL,
    menu_item_id integer NOT NULL,
    quantity integer NOT NULL,
    base_price_snapshot numeric(10,2) NOT NULL,
    unit_price_snapshot numeric(10,2) NOT NULL,
    discount_amount numeric(10,2),
    subtotal numeric(10,2) NOT NULL,
    special_instructions text,
    id integer NOT NULL,
    uuid uuid NOT NULL
);


ALTER TABLE public.menu_order_items OWNER TO opentz;

--
-- Name: menu_order_items_id_seq; Type: SEQUENCE; Schema: public; Owner: opentz
--

CREATE SEQUENCE public.menu_order_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.menu_order_items_id_seq OWNER TO opentz;

--
-- Name: menu_order_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: opentz
--

ALTER SEQUENCE public.menu_order_items_id_seq OWNED BY public.menu_order_items.id;


--
-- Name: menu_order_status_history; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.menu_order_status_history (
    order_id integer NOT NULL,
    status character varying(50) NOT NULL,
    changed_by integer,
    notes text,
    id integer NOT NULL,
    uuid uuid NOT NULL
);


ALTER TABLE public.menu_order_status_history OWNER TO opentz;

--
-- Name: menu_order_status_history_id_seq; Type: SEQUENCE; Schema: public; Owner: opentz
--

CREATE SEQUENCE public.menu_order_status_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.menu_order_status_history_id_seq OWNER TO opentz;

--
-- Name: menu_order_status_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: opentz
--

ALTER SEQUENCE public.menu_order_status_history_id_seq OWNED BY public.menu_order_status_history.id;


--
-- Name: menu_orders; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.menu_orders (
    customer_id integer NOT NULL,
    restaurant_id integer NOT NULL,
    order_number character varying(50) NOT NULL,
    status public.orderstatus NOT NULL,
    order_type public.ordertype NOT NULL,
    subtotal_amount numeric(10,2) NOT NULL,
    discount_total numeric(10,2),
    total_amount numeric(10,2) NOT NULL,
    payment_method public.paymentmethod NOT NULL,
    payment_status public.paymentstatus,
    delivery_address character varying(500),
    special_instructions text,
    applied_offer_id integer,
    applied_coupon_code character varying(50),
    id integer NOT NULL,
    uuid uuid NOT NULL
);


ALTER TABLE public.menu_orders OWNER TO opentz;

--
-- Name: menu_orders_id_seq; Type: SEQUENCE; Schema: public; Owner: opentz
--

CREATE SEQUENCE public.menu_orders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.menu_orders_id_seq OWNER TO opentz;

--
-- Name: menu_orders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: opentz
--

ALTER SEQUENCE public.menu_orders_id_seq OWNED BY public.menu_orders.id;


--
-- Name: menu_restaurants; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.menu_restaurants (
    name character varying(255) NOT NULL,
    description text,
    address_line1 character varying(255),
    address_line2 character varying(255),
    city character varying(100),
    state character varying(100),
    postal_code character varying(20),
    country character varying(2),
    latitude numeric(10,8),
    longitude numeric(11,8),
    cuisine_type character varying(100),
    phone character varying(50),
    email character varying(255),
    logo_url character varying(500),
    opening_hours character varying,
    is_active boolean NOT NULL,
    id integer NOT NULL,
    uuid uuid NOT NULL
);


ALTER TABLE public.menu_restaurants OWNER TO opentz;

--
-- Name: menu_restaurants_id_seq; Type: SEQUENCE; Schema: public; Owner: opentz
--

CREATE SEQUENCE public.menu_restaurants_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.menu_restaurants_id_seq OWNER TO opentz;

--
-- Name: menu_restaurants_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: opentz
--

ALTER SEQUENCE public.menu_restaurants_id_seq OWNED BY public.menu_restaurants.id;


--
-- Name: modules; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.modules (
    name character varying NOT NULL,
    display_name character varying,
    version character varying NOT NULL,
    author character varying,
    description character varying,
    is_enabled boolean NOT NULL,
    base_path_prefix character varying,
    meta_data json,
    id integer NOT NULL,
    uuid uuid NOT NULL
);


ALTER TABLE public.modules OWNER TO opentz;

--
-- Name: modules_id_seq; Type: SEQUENCE; Schema: public; Owner: opentz
--

CREATE SEQUENCE public.modules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.modules_id_seq OWNER TO opentz;

--
-- Name: modules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: opentz
--

ALTER SEQUENCE public.modules_id_seq OWNED BY public.modules.id;


--
-- Name: oauth_sessions; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.oauth_sessions (
    user_id integer NOT NULL,
    family_id character varying NOT NULL,
    refresh_token_id character varying NOT NULL,
    is_rotated boolean NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    device_info character varying,
    ip_address character varying,
    id integer NOT NULL,
    uuid uuid NOT NULL
);


ALTER TABLE public.oauth_sessions OWNER TO opentz;

--
-- Name: oauth_sessions_id_seq; Type: SEQUENCE; Schema: public; Owner: opentz
--

CREATE SEQUENCE public.oauth_sessions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.oauth_sessions_id_seq OWNER TO opentz;

--
-- Name: oauth_sessions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: opentz
--

ALTER SEQUENCE public.oauth_sessions_id_seq OWNED BY public.oauth_sessions.id;


--
-- Name: privileges; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.privileges (
    name character varying NOT NULL,
    description character varying NOT NULL,
    severity character varying NOT NULL,
    id integer NOT NULL,
    uuid uuid NOT NULL
);


ALTER TABLE public.privileges OWNER TO opentz;

--
-- Name: privileges_id_seq; Type: SEQUENCE; Schema: public; Owner: opentz
--

CREATE SEQUENCE public.privileges_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.privileges_id_seq OWNER TO opentz;

--
-- Name: privileges_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: opentz
--

ALTER SEQUENCE public.privileges_id_seq OWNED BY public.privileges.id;


--
-- Name: role_group_roles; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.role_group_roles (
    role_group_id integer NOT NULL,
    role_id integer NOT NULL
);


ALTER TABLE public.role_group_roles OWNER TO opentz;

--
-- Name: role_groups; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.role_groups (
    name character varying NOT NULL,
    description character varying NOT NULL,
    id integer NOT NULL,
    uuid uuid NOT NULL
);


ALTER TABLE public.role_groups OWNER TO opentz;

--
-- Name: role_groups_id_seq; Type: SEQUENCE; Schema: public; Owner: opentz
--

CREATE SEQUENCE public.role_groups_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.role_groups_id_seq OWNER TO opentz;

--
-- Name: role_groups_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: opentz
--

ALTER SEQUENCE public.role_groups_id_seq OWNED BY public.role_groups.id;


--
-- Name: role_privileges; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.role_privileges (
    role_id integer NOT NULL,
    privilege_id integer NOT NULL
);


ALTER TABLE public.role_privileges OWNER TO opentz;

--
-- Name: roles; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.roles (
    name character varying NOT NULL,
    description character varying NOT NULL,
    is_system boolean NOT NULL,
    id integer NOT NULL,
    uuid uuid NOT NULL
);


ALTER TABLE public.roles OWNER TO opentz;

--
-- Name: roles_id_seq; Type: SEQUENCE; Schema: public; Owner: opentz
--

CREATE SEQUENCE public.roles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.roles_id_seq OWNER TO opentz;

--
-- Name: roles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: opentz
--

ALTER SEQUENCE public.roles_id_seq OWNED BY public.roles.id;


--
-- Name: sample_items; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.sample_items (
    name character varying,
    id integer NOT NULL,
    uuid uuid NOT NULL
);


ALTER TABLE public.sample_items OWNER TO opentz;

--
-- Name: sample_items_id_seq; Type: SEQUENCE; Schema: public; Owner: opentz
--

CREATE SEQUENCE public.sample_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sample_items_id_seq OWNER TO opentz;

--
-- Name: sample_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: opentz
--

ALTER SEQUENCE public.sample_items_id_seq OWNED BY public.sample_items.id;


--
-- Name: user_privileges; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.user_privileges (
    user_id integer NOT NULL,
    privilege_id integer NOT NULL
);


ALTER TABLE public.user_privileges OWNER TO opentz;

--
-- Name: user_roles; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.user_roles (
    user_id integer NOT NULL,
    role_id integer NOT NULL
);


ALTER TABLE public.user_roles OWNER TO opentz;

--
-- Name: users; Type: TABLE; Schema: public; Owner: opentz
--

CREATE TABLE public.users (
    username character varying NOT NULL,
    first_name character varying,
    middle_name character varying,
    last_name character varying,
    email character varying NOT NULL,
    password_hash character varying NOT NULL,
    is_active boolean NOT NULL,
    id integer NOT NULL,
    uuid uuid NOT NULL
);


ALTER TABLE public.users OWNER TO opentz;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: opentz
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_id_seq OWNER TO opentz;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: opentz
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: chacc_migration_log id; Type: DEFAULT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.chacc_migration_log ALTER COLUMN id SET DEFAULT nextval('public.chacc_migration_log_id_seq'::regclass);


--
-- Name: menu_activity_logs id; Type: DEFAULT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_activity_logs ALTER COLUMN id SET DEFAULT nextval('public.menu_activity_logs_id_seq'::regclass);


--
-- Name: menu_cart_items id; Type: DEFAULT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_cart_items ALTER COLUMN id SET DEFAULT nextval('public.menu_cart_items_id_seq'::regclass);


--
-- Name: menu_carts id; Type: DEFAULT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_carts ALTER COLUMN id SET DEFAULT nextval('public.menu_carts_id_seq'::regclass);


--
-- Name: menu_categories id; Type: DEFAULT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_categories ALTER COLUMN id SET DEFAULT nextval('public.menu_categories_id_seq'::regclass);


--
-- Name: menu_customers id; Type: DEFAULT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_customers ALTER COLUMN id SET DEFAULT nextval('public.menu_customers_id_seq'::regclass);


--
-- Name: menu_event_pricings id; Type: DEFAULT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_event_pricings ALTER COLUMN id SET DEFAULT nextval('public.menu_event_pricings_id_seq'::regclass);


--
-- Name: menu_items id; Type: DEFAULT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_items ALTER COLUMN id SET DEFAULT nextval('public.menu_items_id_seq'::regclass);


--
-- Name: menu_offer_items id; Type: DEFAULT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_offer_items ALTER COLUMN id SET DEFAULT nextval('public.menu_offer_items_id_seq'::regclass);


--
-- Name: menu_offers id; Type: DEFAULT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_offers ALTER COLUMN id SET DEFAULT nextval('public.menu_offers_id_seq'::regclass);


--
-- Name: menu_order_items id; Type: DEFAULT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_order_items ALTER COLUMN id SET DEFAULT nextval('public.menu_order_items_id_seq'::regclass);


--
-- Name: menu_order_status_history id; Type: DEFAULT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_order_status_history ALTER COLUMN id SET DEFAULT nextval('public.menu_order_status_history_id_seq'::regclass);


--
-- Name: menu_orders id; Type: DEFAULT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_orders ALTER COLUMN id SET DEFAULT nextval('public.menu_orders_id_seq'::regclass);


--
-- Name: menu_restaurants id; Type: DEFAULT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_restaurants ALTER COLUMN id SET DEFAULT nextval('public.menu_restaurants_id_seq'::regclass);


--
-- Name: modules id; Type: DEFAULT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.modules ALTER COLUMN id SET DEFAULT nextval('public.modules_id_seq'::regclass);


--
-- Name: oauth_sessions id; Type: DEFAULT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.oauth_sessions ALTER COLUMN id SET DEFAULT nextval('public.oauth_sessions_id_seq'::regclass);


--
-- Name: privileges id; Type: DEFAULT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.privileges ALTER COLUMN id SET DEFAULT nextval('public.privileges_id_seq'::regclass);


--
-- Name: role_groups id; Type: DEFAULT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.role_groups ALTER COLUMN id SET DEFAULT nextval('public.role_groups_id_seq'::regclass);


--
-- Name: roles id; Type: DEFAULT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.roles ALTER COLUMN id SET DEFAULT nextval('public.roles_id_seq'::regclass);


--
-- Name: sample_items id; Type: DEFAULT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.sample_items ALTER COLUMN id SET DEFAULT nextval('public.sample_items_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Data for Name: chacc_migration_log; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.chacc_migration_log (id, version_num, description, checksum, applied_at, rollback_available) FROM stdin;
13	20260316_162206_add_table_oauth_sessions	CREATE TABLE oauth_sessions	43f30c9952aaee97	2026-03-16 16:22:06.463205	f
14	20260317_120649_add_table_privileges	CREATE TABLE privileges	102c29204f9d27bb	2026-03-17 12:06:49.508174	f
15	20260317_120649_add_table_role_groups	CREATE TABLE role_groups	8f74e0746d50390e	2026-03-17 12:06:49.521138	f
16	20260317_120649_add_table_roles	CREATE TABLE roles	7baef9318156c4e7	2026-03-17 12:06:49.531222	f
17	20260317_120649_add_table_role_group_roles	CREATE TABLE role_group_roles	98aaa33ffd832f98	2026-03-17 12:06:49.537664	f
18	20260317_120649_add_table_role_privileges	CREATE TABLE role_privileges	6d48c32d243b5958	2026-03-17 12:06:49.543987	f
19	20260317_120649_add_table_user_privileges	CREATE TABLE user_privileges	b7d1582ae285528d	2026-03-17 12:06:49.549868	f
20	20260317_120649_add_table_user_roles	CREATE TABLE user_roles	c7de6fc177330910	2026-03-17 12:06:49.555908	f
21	20260519_143239_add_table_sample_items	CREATE TABLE sample_items	5b589bd8220a7030	2026-05-19 14:32:39.72493	f
22	20260519_144051_add_table_sample_items	CREATE TABLE sample_items	6f14a6044603ef92	2026-05-19 14:40:51.825089	f
23	20260520_055542_add_table_menu_restaurants	CREATE TABLE menu_restaurants	8d8d61be0949d87e	2026-05-20 05:55:42.792061	f
24	20260520_055542_add_table_menu_activity_logs	CREATE TABLE menu_activity_logs	d38e3ec4dacf5e9a	2026-05-20 05:55:42.805733	f
25	20260520_055542_add_table_menu_categories	CREATE TABLE menu_categories	4dd1cdf0971afaf3	2026-05-20 05:55:42.816797	f
26	20260520_055542_add_table_menu_customers	CREATE TABLE menu_customers	f1c46ffd35cc7531	2026-05-20 05:55:42.822653	f
27	20260520_055542_add_table_menu_offers	CREATE TABLE menu_offers	b23c761a0e263390	2026-05-20 05:55:42.834929	f
28	20260520_055542_add_table_menu_carts	CREATE TABLE menu_carts	be18d47b58615b8e	2026-05-20 05:55:42.841642	f
29	20260520_055542_add_table_menu_items	CREATE TABLE menu_items	db1455543c5f8d8a	2026-05-20 05:55:42.853042	f
30	20260520_055542_add_table_menu_orders	CREATE TABLE menu_orders	2542b9368809906c	2026-05-20 05:55:42.870163	f
31	20260520_055542_add_table_menu_cart_items	CREATE TABLE menu_cart_items	7d9ae62c07d7a360	2026-05-20 05:55:42.87782	f
32	20260520_055542_add_table_menu_event_pricings	CREATE TABLE menu_event_pricings	774b417840e65253	2026-05-20 05:55:42.889905	f
33	20260520_055542_add_table_menu_offer_items	CREATE TABLE menu_offer_items	3aea69b06bcd9eb1	2026-05-20 05:55:42.896769	f
34	20260520_055542_add_table_menu_order_items	CREATE TABLE menu_order_items	cf6a4852dd0fa978	2026-05-20 05:55:42.910008	f
35	20260520_055542_add_table_menu_order_status_history	CREATE TABLE menu_order_status_history	de654bd7711c9faa	2026-05-20 05:55:42.920822	f
36	20260520_062157_add_table_privileges	CREATE TABLE privileges	c62ad977454e3ce8	2026-05-20 06:21:57.248442	f
37	20260520_062157_add_table_role_groups	CREATE TABLE role_groups	5bcb924cadb639a1	2026-05-20 06:21:57.259412	f
38	20260520_062157_add_table_roles	CREATE TABLE roles	575a7884528292ee	2026-05-20 06:21:57.269569	f
39	20260520_062157_add_table_sample_items	CREATE TABLE sample_items	61cb1e5abb259549	2026-05-20 06:21:57.280359	f
40	20260520_062157_add_table_users	CREATE TABLE users	1630242feb22e65c	2026-05-20 06:21:57.291536	f
41	20260520_062157_add_table_oauth_sessions	CREATE TABLE oauth_sessions	a122668acfc18e26	2026-05-20 06:21:57.30256	f
42	20260520_062157_add_table_role_group_roles	CREATE TABLE role_group_roles	98aaa33ffd832f98	2026-05-20 06:21:57.308304	f
43	20260520_062157_add_table_role_privileges	CREATE TABLE role_privileges	6d48c32d243b5958	2026-05-20 06:21:57.314284	f
44	20260520_062157_add_table_user_privileges	CREATE TABLE user_privileges	b7d1582ae285528d	2026-05-20 06:21:57.321379	f
45	20260520_062157_add_table_user_roles	CREATE TABLE user_roles	c7de6fc177330910	2026-05-20 06:21:57.327356	f
\.


--
-- Data for Name: menu_activity_logs; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.menu_activity_logs (user_id, restaurant_id, action_type, details, ip_address, id, uuid) FROM stdin;
\.


--
-- Data for Name: menu_cart_items; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.menu_cart_items (cart_id, menu_item_id, quantity, unit_price, id, uuid) FROM stdin;
\.


--
-- Data for Name: menu_carts; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.menu_carts (customer_id, restaurant_id, id, uuid) FROM stdin;
\.


--
-- Data for Name: menu_categories; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.menu_categories (restaurant_id, name, description, display_order, image_url, id, uuid) FROM stdin;
\.


--
-- Data for Name: menu_customers; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.menu_customers (user_id, id, uuid) FROM stdin;
\.


--
-- Data for Name: menu_event_pricings; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.menu_event_pricings (menu_item_id, price, starts_at, ends_at, name, is_recurring, recurrence_rule, id, uuid) FROM stdin;
\.


--
-- Data for Name: menu_items; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.menu_items (restaurant_id, category_id, name, description, base_price, current_price, stock_quantity, image_url, is_available, preparation_time, id, uuid) FROM stdin;
\.


--
-- Data for Name: menu_offer_items; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.menu_offer_items (id, offer_id, menu_item_id, uuid) FROM stdin;
\.


--
-- Data for Name: menu_offers; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.menu_offers (restaurant_id, name, description, offer_type, discount_value, minimum_order, maximum_discount, starts_at, ends_at, usage_limit, is_active, id, uuid) FROM stdin;
\.


--
-- Data for Name: menu_order_items; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.menu_order_items (order_id, menu_item_id, quantity, base_price_snapshot, unit_price_snapshot, discount_amount, subtotal, special_instructions, id, uuid) FROM stdin;
\.


--
-- Data for Name: menu_order_status_history; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.menu_order_status_history (order_id, status, changed_by, notes, id, uuid) FROM stdin;
\.


--
-- Data for Name: menu_orders; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.menu_orders (customer_id, restaurant_id, order_number, status, order_type, subtotal_amount, discount_total, total_amount, payment_method, payment_status, delivery_address, special_instructions, applied_offer_id, applied_coupon_code, id, uuid) FROM stdin;
\.


--
-- Data for Name: menu_restaurants; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.menu_restaurants (name, description, address_line1, address_line2, city, state, postal_code, country, latitude, longitude, cuisine_type, phone, email, logo_url, opening_hours, is_active, id, uuid) FROM stdin;
\.


--
-- Data for Name: modules; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.modules (name, display_name, version, author, description, is_enabled, base_path_prefix, meta_data, id, uuid) FROM stdin;
authentication	Authentication Module	0.1.0	Jonas/	A ChaCC module providing authentication functionality.	t	/authentication	{"name": "authentication", "display_name": "Authentication Module", "version": "0.1.0", "author": "Jonas/", "description": "A ChaCC module providing authentication functionality.", "entry_point": "module.main:setup_plugin", "test_entry_point": "module.tests.test_module:run_module_tests", "base_path_prefix": "/authentication", "dependencies_file": "requirements.txt", "required_chacc_version": ">=1.0.0", "license": "MIT", "tags": ["Chacc Official Auth"], "homepage": "https://github.com/Jonas1015/chacc-authentication"}	29	1361b88b-29ce-44e0-a106-6699e11fed7f
\.


--
-- Data for Name: oauth_sessions; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.oauth_sessions (user_id, family_id, refresh_token_id, is_rotated, expires_at, device_info, ip_address, id, uuid) FROM stdin;
\.


--
-- Data for Name: privileges; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.privileges (name, description, severity, id, uuid) FROM stdin;
ALL	Super user privilege that grants all access	CRITICAL	1	29d1da47-7091-49b2-b0eb-ec4eb128dc45
READ_OWN_PROFILE	Read own user profile	LOW	2	cba69433-c163-4486-9cea-b49289c19a39
WRITE_OWN_PROFILE	Modify own user profile	MEDIUM	3	cc4a2f40-82be-49dc-9e8c-44f7bc2a052f
READ_USERS	Read all user profiles	MEDIUM	4	cdba9dfe-f848-4460-ae64-9fd11f6b3b4a
WRITE_USERS	Modify any user profile	HIGH	5	466bee80-54fd-4b78-9257-b7336307bafb
READ_ROLES	Read roles and assignments	MEDIUM	6	846871e1-28a3-41af-aa46-043e1e2de527
WRITE_ROLES	Create/modify roles	HIGH	7	2369cddc-166b-42de-a110-da0e78cc0c59
READ_PRIVILEGES	Read privileges	MEDIUM	8	3e5c63a0-d47d-44d7-b4bb-1d121e23966e
WRITE_PRIVILEGES	Create/modify privileges	VERY HIGH	9	5829c026-4432-403a-9b46-da8dc3695d85
MANAGE_SYSTEM	Full administrative access	CRITICAL	10	adba82dd-b2fe-4546-bd3c-792151833f03
READ_ROLE_GROUPS	Read role groups	MEDIUM	11	6b496104-7014-491b-a475-884d1289731b
WRITE_ROLE_GROUPS	Create/modify role groups	HIGH	12	a9949e73-c70d-4f30-bf91-52ecfee80ab2
WRITE_USER_ROLES	Assign roles to users	HIGH	13	024b0a78-316b-4bc6-9a27-095b19114be3
WRITE_USER_PRIVILEGES	Assign direct privileges to users	HIGH	14	2a880587-dc5c-475a-9089-bb9c5e6fd351
READ_USER_PRIVILEGES	View user's effective privileges	MEDIUM	15	6c89e830-360b-4929-8a85-743ffdd40a88
READ_PASSWORD_POLICY	View password policy	MEDIUM	16	d8b6b127-f303-4256-8578-92b7d6cab531
WRITE_PASSWORD_POLICY	Create/modify password policy	HIGH	17	023e504f-e169-447a-aef5-06a26b6d8f3b
\.


--
-- Data for Name: role_group_roles; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.role_group_roles (role_group_id, role_id) FROM stdin;
\.


--
-- Data for Name: role_groups; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.role_groups (name, description, id, uuid) FROM stdin;
\.


--
-- Data for Name: role_privileges; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.role_privileges (role_id, privilege_id) FROM stdin;
1	1
1	10
2	2
2	3
3	2
3	3
3	4
\.


--
-- Data for Name: roles; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.roles (name, description, is_system, id, uuid) FROM stdin;
ADMIN	Full system administrator with all privileges	t	1	2bb3baf3-d84c-4c67-9c32-f62980516f4a
USER	Standard user with basic profile access	t	2	48ff53b7-574b-45df-9393-1a19782de849
POWER_USER	Power user with extended privileges	t	3	9740aa55-5f24-41d5-85ff-dfa581184219
\.


--
-- Data for Name: sample_items; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.sample_items (name, id, uuid) FROM stdin;
\.


--
-- Data for Name: user_privileges; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.user_privileges (user_id, privilege_id) FROM stdin;
\.


--
-- Data for Name: user_roles; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.user_roles (user_id, role_id) FROM stdin;
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: opentz
--

COPY public.users (username, first_name, middle_name, last_name, email, password_hash, is_active, id, uuid) FROM stdin;
admin	\N	\N	\N	admin@chacc.local	$argon2id$v=19$m=65536,t=3,p=4$p9+fxRwSXeEwNK0XPAZ/Jg$lBLzrQ3Pwkf4dzqSloLFpVco6+28rIdobAezOLE2ZLM	t	1	d30af371-c34b-45bd-89f9-57ba6e89b9bf
\.


--
-- Name: chacc_migration_log_id_seq; Type: SEQUENCE SET; Schema: public; Owner: opentz
--

SELECT pg_catalog.setval('public.chacc_migration_log_id_seq', 45, true);


--
-- Name: menu_activity_logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: opentz
--

SELECT pg_catalog.setval('public.menu_activity_logs_id_seq', 1, false);


--
-- Name: menu_cart_items_id_seq; Type: SEQUENCE SET; Schema: public; Owner: opentz
--

SELECT pg_catalog.setval('public.menu_cart_items_id_seq', 1, false);


--
-- Name: menu_carts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: opentz
--

SELECT pg_catalog.setval('public.menu_carts_id_seq', 1, false);


--
-- Name: menu_categories_id_seq; Type: SEQUENCE SET; Schema: public; Owner: opentz
--

SELECT pg_catalog.setval('public.menu_categories_id_seq', 1, false);


--
-- Name: menu_customers_id_seq; Type: SEQUENCE SET; Schema: public; Owner: opentz
--

SELECT pg_catalog.setval('public.menu_customers_id_seq', 1, false);


--
-- Name: menu_event_pricings_id_seq; Type: SEQUENCE SET; Schema: public; Owner: opentz
--

SELECT pg_catalog.setval('public.menu_event_pricings_id_seq', 1, false);


--
-- Name: menu_items_id_seq; Type: SEQUENCE SET; Schema: public; Owner: opentz
--

SELECT pg_catalog.setval('public.menu_items_id_seq', 1, false);


--
-- Name: menu_offer_items_id_seq; Type: SEQUENCE SET; Schema: public; Owner: opentz
--

SELECT pg_catalog.setval('public.menu_offer_items_id_seq', 1, false);


--
-- Name: menu_offers_id_seq; Type: SEQUENCE SET; Schema: public; Owner: opentz
--

SELECT pg_catalog.setval('public.menu_offers_id_seq', 1, false);


--
-- Name: menu_order_items_id_seq; Type: SEQUENCE SET; Schema: public; Owner: opentz
--

SELECT pg_catalog.setval('public.menu_order_items_id_seq', 1, false);


--
-- Name: menu_order_status_history_id_seq; Type: SEQUENCE SET; Schema: public; Owner: opentz
--

SELECT pg_catalog.setval('public.menu_order_status_history_id_seq', 1, false);


--
-- Name: menu_orders_id_seq; Type: SEQUENCE SET; Schema: public; Owner: opentz
--

SELECT pg_catalog.setval('public.menu_orders_id_seq', 1, false);


--
-- Name: menu_restaurants_id_seq; Type: SEQUENCE SET; Schema: public; Owner: opentz
--

SELECT pg_catalog.setval('public.menu_restaurants_id_seq', 1, false);


--
-- Name: modules_id_seq; Type: SEQUENCE SET; Schema: public; Owner: opentz
--

SELECT pg_catalog.setval('public.modules_id_seq', 29, true);


--
-- Name: oauth_sessions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: opentz
--

SELECT pg_catalog.setval('public.oauth_sessions_id_seq', 1, false);


--
-- Name: privileges_id_seq; Type: SEQUENCE SET; Schema: public; Owner: opentz
--

SELECT pg_catalog.setval('public.privileges_id_seq', 17, true);


--
-- Name: role_groups_id_seq; Type: SEQUENCE SET; Schema: public; Owner: opentz
--

SELECT pg_catalog.setval('public.role_groups_id_seq', 1, false);


--
-- Name: roles_id_seq; Type: SEQUENCE SET; Schema: public; Owner: opentz
--

SELECT pg_catalog.setval('public.roles_id_seq', 3, true);


--
-- Name: sample_items_id_seq; Type: SEQUENCE SET; Schema: public; Owner: opentz
--

SELECT pg_catalog.setval('public.sample_items_id_seq', 1, false);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: opentz
--

SELECT pg_catalog.setval('public.users_id_seq', 1, true);


--
-- Name: chacc_migration_log chacc_migration_log_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.chacc_migration_log
    ADD CONSTRAINT chacc_migration_log_pkey PRIMARY KEY (id);


--
-- Name: chacc_migration_log chacc_migration_log_version_num_key; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.chacc_migration_log
    ADD CONSTRAINT chacc_migration_log_version_num_key UNIQUE (version_num);


--
-- Name: menu_activity_logs menu_activity_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_activity_logs
    ADD CONSTRAINT menu_activity_logs_pkey PRIMARY KEY (id);


--
-- Name: menu_cart_items menu_cart_items_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_cart_items
    ADD CONSTRAINT menu_cart_items_pkey PRIMARY KEY (id);


--
-- Name: menu_carts menu_carts_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_carts
    ADD CONSTRAINT menu_carts_pkey PRIMARY KEY (id);


--
-- Name: menu_categories menu_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_categories
    ADD CONSTRAINT menu_categories_pkey PRIMARY KEY (id);


--
-- Name: menu_customers menu_customers_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_customers
    ADD CONSTRAINT menu_customers_pkey PRIMARY KEY (id);


--
-- Name: menu_event_pricings menu_event_pricings_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_event_pricings
    ADD CONSTRAINT menu_event_pricings_pkey PRIMARY KEY (id);


--
-- Name: menu_items menu_items_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_items
    ADD CONSTRAINT menu_items_pkey PRIMARY KEY (id);


--
-- Name: menu_offer_items menu_offer_items_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_offer_items
    ADD CONSTRAINT menu_offer_items_pkey PRIMARY KEY (id);


--
-- Name: menu_offers menu_offers_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_offers
    ADD CONSTRAINT menu_offers_pkey PRIMARY KEY (id);


--
-- Name: menu_order_items menu_order_items_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_order_items
    ADD CONSTRAINT menu_order_items_pkey PRIMARY KEY (id);


--
-- Name: menu_order_status_history menu_order_status_history_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_order_status_history
    ADD CONSTRAINT menu_order_status_history_pkey PRIMARY KEY (id);


--
-- Name: menu_orders menu_orders_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_orders
    ADD CONSTRAINT menu_orders_pkey PRIMARY KEY (id);


--
-- Name: menu_restaurants menu_restaurants_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.menu_restaurants
    ADD CONSTRAINT menu_restaurants_pkey PRIMARY KEY (id);


--
-- Name: modules modules_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.modules
    ADD CONSTRAINT modules_pkey PRIMARY KEY (id);


--
-- Name: oauth_sessions oauth_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.oauth_sessions
    ADD CONSTRAINT oauth_sessions_pkey PRIMARY KEY (id);


--
-- Name: privileges privileges_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.privileges
    ADD CONSTRAINT privileges_pkey PRIMARY KEY (id);


--
-- Name: role_group_roles role_group_roles_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.role_group_roles
    ADD CONSTRAINT role_group_roles_pkey PRIMARY KEY (role_group_id, role_id);


--
-- Name: role_groups role_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.role_groups
    ADD CONSTRAINT role_groups_pkey PRIMARY KEY (id);


--
-- Name: role_privileges role_privileges_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.role_privileges
    ADD CONSTRAINT role_privileges_pkey PRIMARY KEY (role_id, privilege_id);


--
-- Name: roles roles_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);


--
-- Name: sample_items sample_items_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.sample_items
    ADD CONSTRAINT sample_items_pkey PRIMARY KEY (id);


--
-- Name: modules uq_modules_base_path_prefix; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.modules
    ADD CONSTRAINT uq_modules_base_path_prefix UNIQUE (base_path_prefix);


--
-- Name: user_privileges user_privileges_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.user_privileges
    ADD CONSTRAINT user_privileges_pkey PRIMARY KEY (user_id, privilege_id);


--
-- Name: user_roles user_roles_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_pkey PRIMARY KEY (user_id, role_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: opentz
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: ix_modules_name; Type: INDEX; Schema: public; Owner: opentz
--

CREATE UNIQUE INDEX ix_modules_name ON public.modules USING btree (name);


--
-- Name: ix_modules_uuid; Type: INDEX; Schema: public; Owner: opentz
--

CREATE UNIQUE INDEX ix_modules_uuid ON public.modules USING btree (uuid);


--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: pg_database_owner
--

GRANT ALL ON SCHEMA public TO opentz;


--
-- PostgreSQL database dump complete
--

\unrestrict LInjkiKLzXTPLNxl7uSQ83I3J9VortzbSyttc38Xn4MHmtme1bv5geSU78f5dMg

