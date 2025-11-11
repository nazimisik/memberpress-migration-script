# MemberPress Migration Tool

A Python utility for migrating MemberPress data between WordPress sites. This tool remaps product IDs, gateway IDs, and user/subscription IDs while preserving CSV headers and data integrity.

## Features

- **ID Remapping**: Assigns new sequential IDs to members, subscriptions, and transactions
- **Foreign Key Updates**: Automatically updates all foreign key references to match new IDs
- **Product Mapping**: Maps old product/membership IDs to new ones across all files
- **Gateway Mapping**: Maps payment gateway IDs (Stripe, PayPal, Manual, etc.)
- **Multi-value Support**: Handles comma/semicolon/pipe-separated values in membership fields
- **Header Preservation**: Maintains exact CSV header structure from source files
- **External Reference Protection**: Never touches `subscr_id` (external payment gateway subscription ID)
- **Flexible Configuration**: YAML or JSON config files supported

## Requirements

```bash
pip install pyyaml
```

(PyYAML is optional - only required if using YAML config files. JSON configs work without it.)

## Usage

### Basic Command

```bash
python main.py \
  --members members-export.csv \
  --subscriptions subscriptions-export.csv \
  --transactions transactions-export.csv \
  --config config.yaml \
  --outdir output
```

### Command Line Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--members` | Yes | Path to members export CSV file |
| `--subscriptions` | Yes | Path to subscriptions export CSV file |
| `--transactions` | Yes | Path to transactions export CSV file |
| `--config` | Yes | Path to configuration file (YAML or JSON) |
| `--outdir` | Yes | Output directory for processed files |

## Configuration File

Create a `config.yaml` (or `config.json`) file with the following structure:

```yaml
# Product/Membership ID mappings
mappings:
  products:
    "old_product_id_1": "new_product_id_1"    
    "old_product_id_2": "new_product_id_2"    
    "old_product_id_3": "new_product_id_3"   
  
  gateways:
    "old_gateway_id_1": "new_gateway_id_1"  
    "old_gateway_id_2": "new_gateway_id_2" 
    "old_gateway_id_3": "new_gateway_id_3"  

# Starting ID numbers for new sequential IDs
start_ids:
  members: 100         # First member will get ID 100
  subscriptions: 200   # First subscription will get ID 200
  transactions: 300    # First transaction will get ID 300

# Optional: Customize which columns to map
# (If omitted, sensible defaults are used)
product_columns:
  members: ["memberships", "inactive_memberships"]
  subscriptions: ["product_id", "membership_id", "product_name", "membership", "product"]
  transactions: ["product_id", "membership_id", "product_name", "membership", "product"]

gateway_columns:
  subscriptions: ["gateway_id", "gateway"]
  transactions: ["gateway_id", "gateway"]
```

### JSON Configuration Example

```json
{
  "mappings": {
    "products": {
      "old_product_id_1": "new_product_id_1",
      "old_product_id_2": "new_product_id_2"
    },
    "gateways": {
      "old_gateway_id_1": "new_gateway_id_1",
      "old_gateway_id_2": "new_gateway_id_2"
    }
  },
  "start_ids": {
    "members": 100,
    "subscriptions": 200,
    "transactions": 300
  }
}
```

## How It Works

### 1. ID Remapping
The tool assigns new sequential IDs starting from your configured values:
- **Members**: Gets new IDs starting from `start_ids.members`
- **Subscriptions**: Gets new IDs starting from `start_ids.subscriptions`
- **Transactions**: Gets new IDs starting from `start_ids.transactions`

### 2. Foreign Key Updates
All foreign key references are automatically updated:
- `subscriptions.user_id` → Updated to match new member IDs
- `transactions.user_id` → Updated to match new member IDs
- `transactions.sub_id` → Updated to match new subscription IDs
- `subscr_id` → **NEVER CHANGED** (external gateway reference)

### 3. Value Mapping
Product and gateway values are mapped across all relevant columns:
- **Members**: Maps values in `memberships` and `inactive_memberships` fields
- **Subscriptions**: Maps product and gateway IDs/names
- **Transactions**: Maps product and gateway IDs/names

### 4. Multi-value Handling
For fields containing multiple values (e.g., `"membership1, membership2"`), the tool:
- Splits on commas, semicolons, and pipes
- Maps each individual value
- Preserves original separators and spacing
- Rejoins the values

## Output Files

The tool generates three CSV files in your output directory:

- `members_import.csv` - Processed members data
- `subscriptions_import.csv` - Processed subscriptions data
- `transactions_import.csv` - Processed transactions data

All files maintain the exact same headers as the input files.

## Example Output

```
Members:       45 -> output/members_import.csv (ID starts @ 100)
Subscriptions: 78 -> output/subscriptions_import.csv (id starts @ 200)
Transactions:  234 -> output/transactions_import.csv (id starts @ 300)
Done.
```

## CSV Requirements

### Members CSV
- Must have an `ID` or `id` column

### Subscriptions CSV
- Must have an `id` column
- May have `user_id` column (will be remapped)
- May have `subscr_id` column (will NOT be changed)

### Transactions CSV
- Must have an `id` column
- May have `user_id` column (will be remapped)
- May have `sub_id` column (will be remapped)

## Important Notes

 **Critical**: The tool never modifies `subscr_id` fields. This is the external payment gateway subscription identifier and must remain unchanged to maintain payment gateway connections.

 **Safe**: The tool only modifies copies in the output directory - your original files are never touched.

 **Order-Preserving**: The tool maintains the exact order of rows and columns from your source files.

## Use Cases

- Migrating from a staging site to production
- Consolidating multiple MemberPress installations
- Resolving ID conflicts when merging sites
- Migrating between different WordPress installations

## Troubleshooting

### "Config is YAML but PyYAML is not installed"
Install PyYAML: `pip install pyyaml`

### "No rows found in inputs"
- Check that your CSV file paths are correct
- Ensure CSV files are not empty
- Verify CSV files have proper headers

### "Members CSV must have an 'ID' (or 'id') column"
Your members export must include an ID column. Re-export from MemberPress with all fields included.

### IDs not mapping correctly
- Verify your ID mappings in the config file match your source data
- Check for typos in product/gateway IDs
- Ensure IDs are quoted as strings in YAML/JSON

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

GPLv3 License with love - See LICENSE file for details

## Author

@nazimisik

## Support

For issues and questions, please open an issue on GitHub.


