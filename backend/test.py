"""
Database migration and management script for MongoDB (local and Atlas)
Features:
- Sync local MongoDB to MongoDB Atlas (cloud)
- Sync MongoDB Atlas to local MongoDB
- View all data in JSON format (users, products, games, etc.)
- Export data to Excel/CSV format
"""
import asyncio
import json
import csv
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Source (Local MongoDB)
LOCAL_MONGODB_URL = "mongodb://localhost:27017"
LOCAL_DB_NAME = "decidio"

# Destination (MongoDB Atlas)
ATLAS_MONGODB_URL = "mongodb+srv://seskibotdb:qazx1234@cluster0.vklkl.mongodb.net/?appName=Cluster0"
ATLAS_DB_NAME = "decidio"


def serialize_doc(doc):
    """Convert MongoDB document to JSON-serializable format."""
    if isinstance(doc, dict):
        return {key: serialize_doc(value) for key, value in doc.items()}
    elif isinstance(doc, list):
        return [serialize_doc(item) for item in doc]
    elif isinstance(doc, ObjectId):
        return str(doc)
    elif isinstance(doc, datetime):
        return doc.isoformat()
    else:
        return doc


def export_to_csv(collection_name, documents, output_dir="./data/exports"):
    """Export documents to CSV file."""
    if not documents:
        logger.warning(f"No documents to export for collection '{collection_name}'")
        return None
    
    # Create output directory if it doesn't exist
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Flatten and serialize documents
    flattened = []
    for doc in documents:
        flat_doc = serialize_doc(doc)
        flattened.append(flat_doc)
    
    # Get all unique keys (for dynamic CSV columns)
    all_keys = set()
    for doc in flattened:
        if isinstance(doc, dict):
            all_keys.update(doc.keys())
    
    all_keys = sorted(list(all_keys))
    
    # Write to CSV
    filename = f"{output_dir}/{collection_name}.csv"
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=all_keys)
            writer.writeheader()
            for doc in flattened:
                # Handle nested objects by converting to JSON strings
                row = {}
                for key in all_keys:
                    value = doc.get(key, '')
                    if isinstance(value, (dict, list)):
                        row[key] = json.dumps(value)
                    else:
                        row[key] = value
                writer.writerow(row)
        
        logger.info(f"✓ Exported {len(flattened)} documents to {filename}")
        return filename
    except Exception as e:
        logger.error(f"Error exporting to CSV: {e}")
        return None


async def export_collection_to_excel(db_url, collection_name, db_name=LOCAL_DB_NAME, output_dir="./data/exports"):
    """Export a single collection to CSV/Excel format."""
    
    client = AsyncIOMotorClient(db_url)
    
    try:
        await client.admin.command('ping')
        db = client[db_name]
        collection = db[collection_name]
        
        documents = await collection.find({}).to_list(None)
        
        if not documents:
            logger.info(f"Collection '{collection_name}' is empty")
            return None
        
        filename = export_to_csv(collection_name, documents, output_dir)
        return filename
        
    except Exception as e:
        logger.error(f"Error exporting collection: {e}")
        raise
    
    finally:
        client.close()


async def export_all_to_excel(db_url, db_name=LOCAL_DB_NAME, output_dir="./data/exports"):
    """Export all collections to individual CSV files."""
    
    client = AsyncIOMotorClient(db_url)
    
    try:
        await client.admin.command('ping')
        db = client[db_name]
        
        collections = await db.list_collection_names()
        logger.info(f"Found {len(collections)} collections")
        
        exported_files = []
        
        for collection_name in collections:
            collection = db[collection_name]
            documents = await collection.find({}).to_list(None)
            
            if documents:
                filename = export_to_csv(collection_name, documents, output_dir)
                if filename:
                    exported_files.append(filename)
        
        logger.info(f"\n✓ Export completed! {len(exported_files)} CSV files created in {output_dir}")
        logger.info("You can open these files with Excel, Google Sheets, or any spreadsheet application.")
        return exported_files
        
    except Exception as e:
        logger.error(f"Error exporting collections: {e}")
        raise
    
    finally:
        client.close()


async def sync_local_to_atlas():
    """Sync all collections from local MongoDB to MongoDB Atlas."""
    
    # Connect to both instances
    local_client = AsyncIOMotorClient(LOCAL_MONGODB_URL)
    atlas_client = AsyncIOMotorClient(ATLAS_MONGODB_URL)
    
    try:
        # Verify connections
        await local_client.admin.command('ping')
        logger.info("✓ Connected to local MongoDB")
        
        await atlas_client.admin.command('ping')
        logger.info("✓ Connected to MongoDB Atlas")
        
        # Get databases
        local_db = local_client[LOCAL_DB_NAME]
        atlas_db = atlas_client[ATLAS_DB_NAME]
        
        # Get all collection names from local database
        collections = await local_db.list_collection_names()
        logger.info(f"Found {len(collections)} collections: {collections}")
        
        if not collections:
            logger.warning("No collections found in local database!")
            return
        
        # Clone each collection
        for collection_name in collections:
            logger.info(f"\nCloning collection: {collection_name}")
            
            local_collection = local_db[collection_name]
            atlas_collection = atlas_db[collection_name]
            
            # Get all documents from local collection
            documents = await local_collection.find({}).to_list(None)
            logger.info(f"  Found {len(documents)} documents")
            
            if documents:
                # Clear existing documents in Atlas and insert new ones
                await atlas_collection.delete_many({})
                result = await atlas_collection.insert_many(documents, ordered=False)
                logger.info(f"  ✓ Inserted {len(result.inserted_ids)} documents")
            else:
                logger.info(f"  (empty collection)")
        
        logger.info("\n✓ Sync completed successfully (Local → Atlas)!")
        
    except Exception as e:
        logger.error(f"Error during sync: {e}")
        raise
    
    finally:
        # Close connections
        local_client.close()
        atlas_client.close()
        logger.info("Connections closed")


async def sync_atlas_to_local():
    """Sync all collections from MongoDB Atlas to local MongoDB."""
    
    # Connect to both instances
    local_client = AsyncIOMotorClient(LOCAL_MONGODB_URL)
    atlas_client = AsyncIOMotorClient(ATLAS_MONGODB_URL)
    
    try:
        # Verify connections
        await local_client.admin.command('ping')
        logger.info("✓ Connected to local MongoDB")
        
        await atlas_client.admin.command('ping')
        logger.info("✓ Connected to MongoDB Atlas")
        
        # Get databases
        local_db = local_client[LOCAL_DB_NAME]
        atlas_db = atlas_client[ATLAS_DB_NAME]
        
        # Get all collection names from Atlas database
        collections = await atlas_db.list_collection_names()
        logger.info(f"Found {len(collections)} collections in Atlas: {collections}")
        
        if not collections:
            logger.warning("No collections found in Atlas database!")
            return
        
        # Clone each collection
        for collection_name in collections:
            logger.info(f"\nCloning collection: {collection_name}")
            
            local_collection = local_db[collection_name]
            atlas_collection = atlas_db[collection_name]
            
            # Get all documents from Atlas collection
            documents = await atlas_collection.find({}).to_list(None)
            logger.info(f"  Found {len(documents)} documents")
            
            if documents:
                # Clear existing documents in local and insert new ones
                await local_collection.delete_many({})
                result = await local_collection.insert_many(documents, ordered=False)
                logger.info(f"  ✓ Inserted {len(result.inserted_ids)} documents")
            else:
                logger.info(f"  (empty collection)")
        
        logger.info("\n✓ Sync completed successfully (Atlas → Local)!")
        
    except Exception as e:
        logger.error(f"Error during sync: {e}")
        raise
    
    finally:
        # Close connections
        local_client.close()
        atlas_client.close()
        logger.info("Connections closed")


async def view_collection(db_url, collection_name, db_name=LOCAL_DB_NAME):
    """View all documents in a specific collection."""
    
    client = AsyncIOMotorClient(db_url)
    
    try:
        await client.admin.command('ping')
        db = client[db_name]
        collection = db[collection_name]
        
        documents = await collection.find({}).to_list(None)
        
        if not documents:
            logger.info(f"Collection '{collection_name}' is empty")
            print(json.dumps({"message": f"Collection '{collection_name}' is empty"}, indent=2))
            return
        
        # Convert to JSON-serializable format
        serialized = [serialize_doc(doc) for doc in documents]
        
        logger.info(f"Found {len(documents)} documents in '{collection_name}'")
        print(json.dumps(serialized, indent=2))
        
    except Exception as e:
        logger.error(f"Error viewing collection: {e}")
        raise
    
    finally:
        client.close()


async def view_all_collections(db_url, db_name=LOCAL_DB_NAME):
    """View all collections and their documents."""
    
    client = AsyncIOMotorClient(db_url)
    
    try:
        await client.admin.command('ping')
        db = client[db_name]
        
        collections = await db.list_collection_names()
        logger.info(f"Found {len(collections)} collections")
        
        all_data = {}
        
        for collection_name in collections:
            collection = db[collection_name]
            documents = await collection.find({}).to_list(None)
            
            if documents:
                all_data[collection_name] = [serialize_doc(doc) for doc in documents]
                logger.info(f"  {collection_name}: {len(documents)} documents")
            else:
                all_data[collection_name] = []
                logger.info(f"  {collection_name}: (empty)")
        
        print("\n" + "="*60)
        print(json.dumps(all_data, indent=2))
        print("="*60)
        
    except Exception as e:
        logger.error(f"Error viewing collections: {e}")
        raise
    
    finally:
        client.close()


async def get_collection_summary(db_url, db_name=LOCAL_DB_NAME):
    """Get summary of all collections and document counts."""
    
    client = AsyncIOMotorClient(db_url)
    
    try:
        await client.admin.command('ping')
        db = client[db_name]
        
        collections = await db.list_collection_names()
        
        summary = {}
        total_docs = 0
        
        for collection_name in collections:
            collection = db[collection_name]
            count = await collection.count_documents({})
            summary[collection_name] = count
            total_docs += count
        
        logger.info("\n" + "="*60)
        logger.info("DATABASE SUMMARY")
        logger.info("="*60)
        for collection_name, count in summary.items():
            logger.info(f"  {collection_name}: {count} documents")
        logger.info(f"  TOTAL: {total_docs} documents")
        logger.info("="*60)
        
        return summary
        
    except Exception as e:
        logger.error(f"Error getting summary: {e}")
        raise
    
    finally:
        client.close()


def print_menu():
    """Print interactive menu."""
    print("\n" + "="*60)
    print("DATABASE MANAGEMENT TOOL")
    print("="*60)
    print("SYNC OPERATIONS:")
    print("  1. Sync Local → Atlas (upload local data to cloud)")
    print("  2. Sync Atlas → Local (download cloud data to local)")
    print("\nVIEW DATA (JSON):")
    print("  3. View Local Database (all collections)")
    print("  4. View Atlas Database (all collections)")
    print("  5. View Specific Collection (Local)")
    print("  6. View Specific Collection (Atlas)")
    print("\nEXPORT TO EXCEL/CSV:")
    print("  7. Export Local Database to Excel")
    print("  8. Export Atlas to Excel")
    print("  9. Export Specific Collection (Local)")
    print(" 10. Export Specific Collection (Atlas)")
    print("\nDATABASE INFO:")
    print(" 11. Database Summary (Local)")
    print(" 12. Database Summary (Atlas)")
    print("\n  0. Exit")
    print("="*60)


async def main_interactive():
    """Interactive menu for database operations."""
    
    while True:
        print_menu()
        choice = input("Select option (0-12): ").strip()
        
        if choice == "0":
            logger.info("Exiting...")
            break
        
        elif choice == "1":
            logger.info("Starting sync: Local → Atlas")
            print("-" * 60)
            await sync_local_to_atlas()
        
        elif choice == "2":
            logger.info("Starting sync: Atlas → Local")
            print("-" * 60)
            await sync_atlas_to_local()
        
        elif choice == "3":
            logger.info("Fetching all collections from Local MongoDB")
            print("-" * 60)
            await view_all_collections(LOCAL_MONGODB_URL, LOCAL_DB_NAME)
        
        elif choice == "4":
            logger.info("Fetching all collections from Atlas")
            print("-" * 60)
            await view_all_collections(ATLAS_MONGODB_URL, ATLAS_DB_NAME)
        
        elif choice == "5":
            collection = input("Enter collection name (e.g., products, users, games): ").strip()
            if collection:
                logger.info(f"Fetching '{collection}' from Local MongoDB")
                print("-" * 60)
                await view_collection(LOCAL_MONGODB_URL, collection, LOCAL_DB_NAME)
        
        elif choice == "6":
            collection = input("Enter collection name (e.g., products, users, games): ").strip()
            if collection:
                logger.info(f"Fetching '{collection}' from Atlas")
                print("-" * 60)
                await view_collection(ATLAS_MONGODB_URL, collection, ATLAS_DB_NAME)
        
        elif choice == "7":
            logger.info("Exporting Local Database to Excel/CSV")
            print("-" * 60)
            await export_all_to_excel(LOCAL_MONGODB_URL, LOCAL_DB_NAME)
        
        elif choice == "8":
            logger.info("Exporting Atlas Database to Excel/CSV")
            print("-" * 60)
            await export_all_to_excel(ATLAS_MONGODB_URL, ATLAS_DB_NAME)
        
        elif choice == "9":
            collection = input("Enter collection name (e.g., products, users, games): ").strip()
            if collection:
                logger.info(f"Exporting '{collection}' from Local MongoDB to CSV")
                print("-" * 60)
                await export_collection_to_excel(LOCAL_MONGODB_URL, collection, LOCAL_DB_NAME)
        
        elif choice == "10":
            collection = input("Enter collection name (e.g., products, users, games): ").strip()
            if collection:
                logger.info(f"Exporting '{collection}' from Atlas to CSV")
                print("-" * 60)
                await export_collection_to_excel(ATLAS_MONGODB_URL, collection, ATLAS_DB_NAME)
        
        elif choice == "11":
            logger.info("Getting Local Database Summary")
            print("-" * 60)
            await get_collection_summary(LOCAL_MONGODB_URL, LOCAL_DB_NAME)
        
        elif choice == "12":
            logger.info("Getting Atlas Database Summary")
            print("-" * 60)
            await get_collection_summary(ATLAS_MONGODB_URL, ATLAS_DB_NAME)
        
        else:
            logger.warning("Invalid option. Please try again.")
        
        input("\nPress Enter to continue...")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "sync-local-to-atlas":
            logger.info("Starting database sync from local MongoDB to Atlas...")
            logger.info(f"Source: {LOCAL_MONGODB_URL}/{LOCAL_DB_NAME}")
            logger.info(f"Destination: {ATLAS_DB_NAME} on Atlas")
            logger.info("-" * 60)
            asyncio.run(sync_local_to_atlas())
        
        elif command == "sync-atlas-to-local":
            logger.info("Starting database sync from Atlas to local MongoDB...")
            logger.info(f"Source: Atlas/{ATLAS_DB_NAME}")
            logger.info(f"Destination: {LOCAL_MONGODB_URL}/{LOCAL_DB_NAME}")
            logger.info("-" * 60)
            asyncio.run(sync_atlas_to_local())
        
        elif command == "view-local":
            logger.info("Viewing all collections from local MongoDB...")
            asyncio.run(view_all_collections(LOCAL_MONGODB_URL, LOCAL_DB_NAME))
        
        elif command == "view-atlas":
            logger.info("Viewing all collections from Atlas...")
            asyncio.run(view_all_collections(ATLAS_MONGODB_URL, ATLAS_DB_NAME))
        
        elif command == "summary-local":
            logger.info("Getting summary of local MongoDB...")
            asyncio.run(get_collection_summary(LOCAL_MONGODB_URL, LOCAL_DB_NAME))
        
        elif command == "summary-atlas":
            logger.info("Getting summary of Atlas...")
            asyncio.run(get_collection_summary(ATLAS_MONGODB_URL, ATLAS_DB_NAME))
        
        elif command == "export-local":
            logger.info("Exporting all local collections to Excel/CSV...")
            asyncio.run(export_all_to_excel(LOCAL_MONGODB_URL, LOCAL_DB_NAME))
        
        elif command == "export-atlas":
            logger.info("Exporting all Atlas collections to Excel/CSV...")
            asyncio.run(export_all_to_excel(ATLAS_MONGODB_URL, ATLAS_DB_NAME))
        
        elif command == "export-local-collection":
            if len(sys.argv) < 3:
                logger.error("Please provide collection name: python test.py export-local-collection <collection_name>")
            else:
                collection_name = sys.argv[2]
                logger.info(f"Exporting '{collection_name}' from local MongoDB...")
                asyncio.run(export_collection_to_excel(LOCAL_MONGODB_URL, collection_name, LOCAL_DB_NAME))
        
        elif command == "export-atlas-collection":
            if len(sys.argv) < 3:
                logger.error("Please provide collection name: python test.py export-atlas-collection <collection_name>")
            else:
                collection_name = sys.argv[2]
                logger.info(f"Exporting '{collection_name}' from Atlas...")
                asyncio.run(export_collection_to_excel(ATLAS_MONGODB_URL, collection_name, ATLAS_DB_NAME))
        
        else:
            logger.error(f"Unknown command: {command}")
            print("\nAvailable commands:")
            print("  sync-local-to-atlas              - Upload local data to cloud")
            print("  sync-atlas-to-local              - Download cloud data to local")
            print("  view-local                       - View all local collections (JSON)")
            print("  view-atlas                       - View all cloud collections (JSON)")
            print("  summary-local                    - Count documents in local DB")
            print("  summary-atlas                    - Count documents in cloud DB")
            print("  export-local                     - Export local DB to Excel/CSV")
            print("  export-atlas                     - Export cloud DB to Excel/CSV")
            print("  export-local-collection <name>   - Export specific local collection")
            print("  export-atlas-collection <name>   - Export specific cloud collection")
            print("\nOr run without arguments for interactive mode:")
            print("  python test.py")
    
    else:
        # Interactive mode
        asyncio.run(main_interactive())
