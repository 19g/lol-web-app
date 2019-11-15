**Databases 4111.001 Project - League of Legends Database**

Postgresql server: `postgresql://jcr1298:garen@35.243.220.243/proj1part2`  
URL: `35.231.120.5:8111/`  
We implemented all the parts of our proposal from part 1 and reached our stretch goal, although in a different manner. We originally thought we might need to use computer vision to analyze the TFT side of the game but an additional API for TFT was released making that unnecessary.  
Interesting pages: The most interesting pages for us are the analysis pages for TFT and SR respectively. TFT and SR are the two different game modes we based our database on and using the options on our pages, a player can determine their results based on specific criteria. For example, a player can find their win rate on a specific champion, or if there is a correlation between achieving the first inhibitor kill and winning. Similarly, with TFT, a player can see with which team compositions they are most likely to win or "top four" with.  

To run, type `python3 server.py`  
To show help, type `python3 server.py --help`

Create a config.py file with variable api_key set to value of personal Riot API key

Packages that need to be included are  
`click`  
`flask`  
`psycopg2`  
`requests`  
`datetime`  
`sqlalchemy`