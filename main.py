import dotenv

dotenv.load_dotenv()

from amzn_selling_partner.vendor import orders as vendor_orders

vendor_orders_client = vendor_orders.Client()

print(vendor_orders_client.get_purchase_orders())
