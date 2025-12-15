# gsm_gate
Pro běh __Django-admin__ nejprve vytvořím __superusera__. 
Pro vytvoření: 
1. spustit projekt v docker-compose
2. switch do kontejneru: *docker-compose exec <name servise from docker-compose> /bin/bash
3. __python manage.py migrate__
4. __python manage.py createsuperuser__

