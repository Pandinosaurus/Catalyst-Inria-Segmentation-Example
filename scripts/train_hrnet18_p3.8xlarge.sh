python fit_predict.py -m hrnet18 -b 64 -w 24 -dd /home/ubuntu/data/inria/AerialImageDataset --size 512 -s cos -o RAdam -a hard -lr 1e-3 -e 200 -d 0.1 --criterion bce 1 -v