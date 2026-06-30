# Rajendra Save Restricted Bot
# Owner: RAJENDRA

import motor.motor_asyncio
from config import DB_NAME, DB_URI

class Database:

    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db.users

    def new_user(self, id, name):
        return dict(
            id=int(id),
            name=name,
            session=None,
            api_id=None,
            api_hash=None,
            thumb_file_id=None,
            custom_title=None,
            find_replace=[],
            remove_words=[]
        )

    async def add_user(self, id, name):
        user = self.new_user(id, name)
        await self.col.update_one({'id': int(id)}, {'$setOnInsert': user}, upsert=True)

    async def get_user(self, id):
        return await self.col.find_one({'id': int(id)})

    async def is_user_exist(self, id):
        user = await self.col.find_one({'id':int(id)})
        return bool(user)

    async def total_users_count(self):
        count = await self.col.count_documents({})
        return count

    async def get_all_users(self):
        return self.col.find({})

    async def delete_user(self, user_id):
        await self.col.delete_many({'id': int(user_id)})

    async def set_session(self, id, session):
        await self.col.update_one({'id': int(id)}, {'$set': {'session': session}}, upsert=True)

    async def get_session(self, id):
        user = await self.get_user(id)
        return user.get('session') if user else None

    async def set_api_id(self, id, api_id):
        await self.col.update_one({'id': int(id)}, {'$set': {'api_id': api_id}}, upsert=True)

    async def get_api_id(self, id):
        user = await self.get_user(id)
        return user.get('api_id') if user else None

    async def set_api_hash(self, id, api_hash):
        await self.col.update_one({'id': int(id)}, {'$set': {'api_hash': api_hash}}, upsert=True)

    async def get_api_hash(self, id):
        user = await self.get_user(id)
        return user.get('api_hash') if user else None

    # ---------- Customization settings ----------

    async def set_thumb(self, id, file_id):
        await self.col.update_one({'id': int(id)}, {'$set': {'thumb_file_id': file_id}}, upsert=True)

    async def get_thumb(self, id):
        user = await self.get_user(id)
        return user.get('thumb_file_id') if user else None

    async def set_custom_title(self, id, title):
        await self.col.update_one({'id': int(id)}, {'$set': {'custom_title': title}}, upsert=True)

    async def get_custom_title(self, id):
        user = await self.get_user(id)
        return user.get('custom_title') if user else None

    async def add_find_replace(self, id, find, replace):
        # Replace existing rule with same `find` if it exists
        await self.col.update_one(
            {'id': int(id)},
            {'$pull': {'find_replace': {'find': find}}}
        )
        await self.col.update_one(
            {'id': int(id)},
            {'$push': {'find_replace': {'find': find, 'replace': replace}}}
        )

    async def get_find_replace(self, id):
        user = await self.get_user(id)
        return user.get('find_replace', []) if user else []

    async def clear_find_replace(self, id):
        await self.col.update_one({'id': int(id)}, {'$set': {'find_replace': []}})

    async def add_remove_word(self, id, word):
        await self.col.update_one(
            {'id': int(id)},
            {'$pull': {'remove_words': word}}
        )
        await self.col.update_one(
            {'id': int(id)},
            {'$push': {'remove_words': word}}
        )

    async def get_remove_words(self, id):
        user = await self.get_user(id)
        return user.get('remove_words', []) if user else []

    async def clear_remove_words(self, id):
        await self.col.update_one({'id': int(id)}, {'$set': {'remove_words': []}})

db = Database(DB_URI, DB_NAME)

# Rajendra Save Restricted Bot
# Owner: RAJENDRA
