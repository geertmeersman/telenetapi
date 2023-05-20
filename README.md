# telenetapi

Python library to communicate with the Telenet API

## API Example

```python
"""Test for telenetapi."""
from telenetapi import TelenetClient

import  asyncio
import json

async def main():

    client = TelenetClient('<login>', '<password>', 'nl')  # language in ['en', 'nl', 'fr']
    userdetails = client.login()
    print(f"{userdetails.get('first_name')} {userdetails.get('last_name')}")
    client.get_data()
    print(json.dumps(client.data, indent=2))

asyncio.run(main())
```
