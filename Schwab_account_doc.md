I’ve explored the account‑documentation page for the Schwab Trader API on the Schwab Developer Portal. Below is a high‑level summary.

## Overview

* **API name**: Trader API – Account Access and User Preferences.
* **Purpose**: Provides endpoints for retail clients to retrieve account data (balances, positions), manage orders and user preferences, and carry out trades.
* **Specification version**: **1.0.0** (OpenAPI 3.0).
* **Base server**: All production requests are sent to `https://api.schwabapi.com/trader/v1` .
* The documentation makes clear that account numbers in plain text are *not* used in requests; instead, a “plain‑text/encrypted value” pair is fetched first and the encrypted value is used for subsequent calls.

## Key endpoints

| Endpoint (method & path)                            | Purpose                                                                             | Notes                                                                                                                                                   |
| --------------------------------------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /accounts/accountNumbers`                      | Returns a list of account numbers and their encrypted values.                       | First call required, since plain‑text account numbers cannot be used in subsequent calls. The response includes `accountNumber` and `hashValue` fields. |
| `GET /accounts`                                     | Retrieves balances and positions for all accounts linked to the authenticated user. | Accepts optional query parameters (not shown in screenshot) to customize fields returned.                                                               |
| `GET /accounts/{accountNumber}`                     | Retrieves the balance and positions for a specific account.                         | Uses the encrypted account number returned from the first endpoint.                                                                                     |
| `GET /accounts/{accountNumber}/orders`              | Lists all orders for a specific account.                                            | Typically returns pending, filled and canceled orders.                                                                                                  |
| `POST /accounts/{accountNumber}/orders`             | Places a new order for a specified account.                                         | Requires order details such as symbol, quantity, price, order type, etc.                                                                                |
| `GET /accounts/{accountNumber}/orders/{orderId}`    | Retrieves detailed information about a specific order.                              | Useful to check order status.                                                                                                                           |
| `DELETE /accounts/{accountNumber}/orders/{orderId}` | Cancels an existing order.                                                          | Only works on orders that haven’t executed.                                                                                                             |
| `PUT /accounts/{accountNumber}/orders/{orderId}`    | Replaces or modifies an existing order.                                             | Must provide updated order parameters.                                                                                                                  |
| `POST /accounts/{accountNumber}/previewOrder`       | Previews an order before submission.                                                | Returns an estimate of cost and verifies order parameters.                                                                                              |

## Additional details

* **Authorization**: Uses OAuth 2.0 (three‑legged). Applications must be registered in the Schwab Developer Portal, specifying redirect URIs and obtaining client credentials.
* **Error handling**: Common HTTP responses include 400 (validation errors), 401 (invalid token or unauthorized), 404 (resource not found), and 500 (server error). Responses include a `message` and an `errors` list.
* **Headers**: Each call includes a `Schwab-Client-CorrelId` header for correlation/tracing (auto‑generated).
* **Use of encrypted account numbers**: The documentation stresses that account numbers must be encrypted. Clients should call the account‑numbers endpoint first and then use the returned `hashValue` for all other requests.

This summary should help you understand the available endpoints and the key operational requirements of the Schwab Trader API’s account and trading specification.
