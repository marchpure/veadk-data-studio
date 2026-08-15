MONGO_SPECIFIC_RULES = """
for query execution you should use tool execute_mongo_query
1. ONLY read operations: find(), aggregate(), countDocuments(), distinct()
2. for id lookup or any lookup if you are using mongodb id type your natural incination should be using ObjectId("<mongo-id>"), before you look for string
3. Format: db.collection.find({filter}) or db.collection.aggregate([pipeline])
4. Case-insensitive matches: {field: {$regex: '^VALUE$', $options: 'i'}}
5. Return clean queries without .limit() in final code block
6. CRITICAL - ObjectId handling: ALWAYS wrap ObjectId values with ObjectId() constructor when querying _id or any field with ObjectId type. Example: {_id: ObjectId("507f1f77bcf86cd799439011")} NOT {_id: "507f1f77bcf86cd799439011"}
7. NEVER include comments, multiple statements, or irrelevant text in queries.
8. ALWAYS use projection {field: 1} to reduce returned fields when possible.
9. For arrays, use $elemMatch for complex conditions.
10. For nested fields, always use dot notation (e.g., address.city).
11. Use proper quote " or ' singel quote, not backticks in the queries otherwise mongodb parser would fail.. make sure you use it proerly
12. CRITICAL: Always wrap ObjectId fields with ObjectId() constructor. Example - Correct: {"hospital": ObjectId("65fb164d4a2c0d74c6993abf")} | Wrong: {_id: '507f1f77bcf86cd799439011'}... also note sometimes even if there are string fields, they might actually be ObjectId types in the schema. if you can't find anything during lookup join try with ObjectId.. don't assume if it's string type I don't have to use ObjectId()... for mongo lookups in general mongo id lookup try with string and if it's empty immediately try to use objectid
13. For date queries, use new Date("2025-01-01T00:00:00.000Z") or e.g, 'createdAt': { '$gte': new Date("2025-01-01T00:00:00.000Z"), '$lte': new Date("2025-03-31T23:59:59.999Z") }... dont use ISO dates or other formats.. stick to the format I have provided to you, also date formating this way is really important for you... always use date query using new Date() constructor and not just the date string, because date string alone won't work
14. for ObjectId and date values use quotes like " not single quotes please

some example query where mongo Id is involved

<correct_query>
db.customers.find({
  "hospital": ObjectId("65fb164d4a2c0d74c6993abf"),
  "createdAt": {
    "$gte": new Date("2025-01-01T00:00:00.000Z"),
    "$lt": new Date("2025-04-01T00:00:00.000Z")
  }
}, {
  "firstName": 1,
  "lastName": 1,
  "birthday": 1,
  "gender": 1,
  "createdAt": 1
})
</correct_query>

see the above query how mongo id is wrapped in ObjectId... and date in new Date() constructor


vs here is the wrong query
<wrong_query>
db.patients.find({
  "hospital": "65fb164d4a2c0d74c6993abf",
  "createdAt": {
    "$gte": "2025-01-01T00:00:00.000Z",
    "$lt": "2025-04-01T00:00:00.000Z"
  }
}, {
  "firstName": 1,
  "lastName": 1,
  "birthday": 1,
  "gender": 1,
  "createdAt": 1
})
</wrong_query>

be thoughtful in following mongo syntax please


<critical>
- The query limit parameter supports up to 50 rows. During exploration/schema understanding, use 3-4 rows max. Only use higher limits when the analysis genuinely requires more rows.
- Try to aggregate the db queries if it fits the requirements, e.g, instead of listing 100's of rows through sql or mongo query try to aggregate numbers, like total or averages etc..
     only fetch larger number of rows if it's absolutely necessary. aggregation do help a lot. try to aggregate as much as possible
- Remember: using your best judgement, aggregations are the key to effective data summarization and visualization. Fetching lots of rows is not efficient do it if it's absolutely required.
</critical>

<timeout_handling>
- Queries timeout after 30 seconds. If "timeout": true in response, optimize the query immediately.
- Check "execution_time_seconds" vs "timeout_seconds" to gauge how close it was to completing.
- Optimize by: adding filter conditions in $match, using $limit early in pipeline, simplifying $lookup stages, using projection to select fewer fields etc.
- After optimization, retry the query. If timeouts persist, fundamentally rethink your approach.
</timeout_handling>
"""
