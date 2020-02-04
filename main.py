from query import query_tweets

# Query for tweets with the keyword adidas in it and then print the text and the respective number of likes for every tweet

list_of_tweets = query_tweets("Adidas", 50, lang='en')
# print the retrieved tweets to the screen:
for tweet in list_of_tweets:
    print(tweet.text + " " + str(tweet.likes))
