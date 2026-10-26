import matplotlib.pyplot as plt

plt.ion()

fig, ax = plt.subplots()

ax.set_title("Prueba de radar LiDAR")
ax.set_xlim(0, 7)
ax.set_ylim(0, 7)
ax.grid(True)

plt.show(block=True)