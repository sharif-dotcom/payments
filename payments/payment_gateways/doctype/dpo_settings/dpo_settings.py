# Copyright (c) 2025, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from xml.etree.ElementTree import fromstring
import requests


class DPOSettings(Document):
    def validate(self):
        """Ensure all required credentials are set."""
        required_fields = ["company_token", "service_id", "dpo_url", "payment_currency", "back_url", "redirect_url"]
        missing_fields = [field for field in required_fields if not self.get(field)]
        if missing_fields:
            frappe.throw(_("Missing required fields: {0}".format(", ".join(missing_fields))))
        
        self.validate_currency(self.payment_currency)
        self.validate_url(self.dpo_url)
        self.validate_url(self.redirect_url)

    def validate_url(self, url):
        """Check if the provided URL is reachable."""
        try:
            response = requests.get(url)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            frappe.throw(_("Error connecting to DPO URL: {0}".format(e)))

    def validate_currency(self, currency):
        """Ensure the given currency is supported."""
        supported_currencies = ['USD', 'EUR', 'GBP', 'ZAR', 'KES', 'UGX']
        if currency not in supported_currencies:
            frappe.throw(_("Currency '{0}' is not supported. Supported currencies: {1}".format(currency, ", ".join(supported_currencies))))

    def get_payment_url(self, **payment_details):
        """
        Generate the payment URL for DPO using XML payload.
        """
        # Ensure necessary fields are present
        required_fields = ["amount", "currency", "payment", "redirect_to", "description"]
        for field in required_fields:
            if field not in payment_details or not payment_details.get(field):
                frappe.throw(f"Missing required payment detail: {field}")

        # Create the XML payload as a string with dynamic values
        xml = f'''<?xml version="1.0" encoding="utf-8"?>
        <API3G>
            <CompanyToken>{self.company_token}</CompanyToken>
            <Request>createToken</Request>
            <Transaction>
                <PaymentAmount>{payment_details['amount']}</PaymentAmount>
                <PaymentCurrency>{payment_details['currency']}</PaymentCurrency>
                <CompanyRef>{payment_details['payment']}</CompanyRef>  <!-- Payment reference ID -->
                <RedirectURL>{self.redirect_url}</RedirectURL>
                <BackURL>{self.back_url}</BackURL>
                <CompanyRefUnique>0</CompanyRefUnique>
                <PTL>5</PTL>  <!-- Payment Time Limit in minutes -->
            </Transaction>
            <Services>
                <Service>
                    <ServiceType>{self.service_id}</ServiceType>  <!-- Example service type -->
                    <ServiceDescription>{payment_details['description']}</ServiceDescription>
                    <ServiceDate>{frappe.utils.now_datetime().strftime("%Y/%m/%d %H:%M")}</ServiceDate>
                </Service>
            </Services>
        </API3G>'''

        headers = {'Content-Type': 'application/xml'}


        print("on making the post request ")
        # Make the API request to DPO
        try:
            response = requests.post(self.dpo_url, data=xml, headers=headers)
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx, 5xx)
        except requests.exceptions.RequestException as e:
            frappe.throw(f"Failed to create DPO payment: {e}")

        if response.status_code == 200:
            # Parse the response XML to get the transaction token
            transaction_token = self._parse_xml_response(response.text, "TransToken")
            if transaction_token:
                payment_url = f"https://secure.3gdirectpay.com/payv2.php?ID={transaction_token}"
                return payment_url
            else:
                frappe.throw("Failed to retrieve transaction token from DPO response.")
        else:
            frappe.throw(f"Failed to create DPO payment. Status Code: {response.status_code}, Response: {response.text}")

    def _parse_xml_response(self, xml_string, tag):
        """
        Parse the XML response and extract the value of a specific tag.
        """
        try:
            root = fromstring(xml_string)
            return root.find(tag).text if root.find(tag) is not None else None
        except Exception as e:
            frappe.throw(f"Error parsing XML response: {e}")

    
# this is not in use for now.....
# just still looking at how we can use it(functional)

def verify_transaction_token(self, transaction_token, company_token):
        """
        Verify the transaction token using DPO's API and return the transaction status.
        """
        url = "https://secure.3gdirectpay.com/API/v6/"  

        # Constructing XML request data for the transaction
        xml_data = f"""<?xml version="1.0" encoding="utf-8"?>
        <API3G>
          <CompanyToken>{company_token}</CompanyToken>
          <Request>verifyToken</Request>
          <TransactionToken>{transaction_token}</TransactionToken>
        </API3G>"""

        headers = {"Content-Type": "application/xml"}

        try:
            # Make the POST request to the DPO endpoint
            response = requests.post(url, data=xml_data, headers=headers)

            # Parse the response XML
            if response.status_code == 200:
                result = self.parse_dpo_response(response.text)

                # If the transaction is authorized or captured
                if result == "authorized":
                    return "authorized"
                elif result == "captured":
                    return "captured"
                elif result == "refunded":
                    return "refunded"
                else:
                    return "failed"
            else:
                frappe.log_error(f"Error in DPO Response: {response.text}", title="DPO Verification Failed")
                return "failed"
        except requests.exceptions.RequestException as e:
            frappe.log_error(f"Error verifying transaction: {e}", title="DPO Verification Failed")
            return "failed"

def parse_dpo_response(self, response_text):
        """
        Parse the XML response from DPO and extract the result.
        """
        # Assuming the response is XML
        try:
            root = fromstring(response_text)
            result = root.find("Result").text

            if result == "900":
                return "authorized"
            elif result == "400":
                return "captured"
            elif result == "500":
                return "refunded"
            else:
                return "failed"
        except Exception as e:
            frappe.log_error(f"Error parsing DPO response: {str(e)}", title="DPO Response Parsing Error")
            return "failed"



